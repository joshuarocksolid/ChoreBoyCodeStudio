"""Dulwich facade. This is the only Team Sync module that imports dulwich."""

from __future__ import annotations

import io
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from dulwich.diff_tree import tree_changes
from dulwich.graph import find_merge_base
from dulwich.ignore import IgnoreFilterManager
from dulwich.index import ConflictedIndexEntry, index_entry_from_stat, update_working_tree
from dulwich.object_store import iter_tree_contents
from dulwich.objects import Blob, Commit, Tag
from dulwich.porcelain import annotate
from dulwich.repo import Repo
from dulwich.stash import Stash

from app.features.team_sync.api import (
    FILE_ADDED,
    FILE_DELETED,
    FILE_MODIFIED,
    BlameLine,
    Change,
    FileChange,
    FileDiff,
    SetAside,
)
from app.features.team_sync.core import TeamSyncError
from app.features.team_sync.core.mailbox import atomic_write_bytes
from app.features.team_sync.core.merge3way import (
    WHOLE_FILE_BYTES,
    diff_hunks,
    inspect_text,
    is_binary_payload,
)

_AUTHOR_TRAILER = "CBCS-Shop: "
_STATION_TRAILER = "CBCS-Station: "


class TeamRepo:
    def __init__(self, project_root: str) -> None:
        self.root = str(project_root)
        self._cached: Optional[Repo] = None
        self._ignore_mgr: Optional[IgnoreFilterManager] = None
        self._ignore_key: Optional[int] = None
        self._blame_cache: Dict[Tuple[str, str], List[BlameLine]] = {}

    def exists(self) -> bool:
        return (Path(self.root) / ".git").is_dir()

    def init_repo(self) -> None:
        if self.exists():
            return
        Path(self.root).mkdir(parents=True, exist_ok=True)
        repo = Repo.init(self.root, default_branch=b"refs/heads/main")
        config = repo.get_config()
        config.set((b"commit",), b"gpgsign", b"false")
        config.write_to_path()
        self._cached = repo

    def head_sha(self) -> Optional[str]:
        if not self.exists():
            return None
        try:
            return self._repo().head().decode("ascii")
        except KeyError:
            return None

    def branch_name(self) -> str:
        if not self.exists():
            return "main"
        raw = self._repo().refs.read_ref(b"HEAD")
        if raw is None:
            return "main"
        text = raw.decode("utf-8", "replace")
        prefix = "ref: refs/heads/"
        if text.startswith(prefix):
            return text[len(prefix) :]
        return "main"

    def branch_names(self) -> List[str]:
        if not self.exists():
            return []
        names: List[str] = []
        for ref in self._repo().refs.allkeys():
            if ref.startswith(b"refs/heads/"):
                names.append(ref[len(b"refs/heads/") :].decode("utf-8"))
        return sorted(names)

    def experiment_names(self) -> List[str]:
        return [name for name in self.branch_names() if name.startswith("exp/")]

    def status(self) -> List[FileChange]:
        if not self.exists():
            return []
        head = self.head_sha()
        head_files = self._tree_shas(head)
        index = self._repo().open_index()
        seen = set()
        changes: List[FileChange] = []
        for rel in self._iter_work_files():
            seen.add(rel)
            try:
                work_sha = self._work_sha(index, rel)
            except OSError:
                continue
            committed = head_files.get(rel)
            if committed is None:
                changes.append(FileChange(rel, FILE_ADDED))
            elif work_sha != committed:
                changes.append(FileChange(rel, FILE_MODIFIED))
        for rel in head_files:
            if rel not in seen:
                changes.append(FileChange(rel, FILE_DELETED))
        changes.sort(key=lambda item: item.path)
        return changes

    def dirty(self) -> bool:
        return bool(self.status())

    def commit(
        self,
        note: str,
        author_name: str,
        author_email: str,
        shop_id: str,
        station: str,
        when: datetime,
        paths: Optional[Sequence[str]] = None,
        extra_parents: Optional[Sequence[str]] = None,
    ) -> str:
        if not self.exists():
            raise TeamSyncError("Share the project before saving a change.")
        changes = self.status()
        if paths is not None:
            wanted = set(paths)
            changes = [item for item in changes if item.path in wanted]
        if not changes and not extra_parents:
            raise TeamSyncError("Nothing to save.")
        repo = self._repo()
        if changes:
            repo.get_worktree().stage([item.path for item in changes])
        author = f"{author_name} <{author_email}>".encode("utf-8")
        moment = when if when.tzinfo is not None else when.replace(tzinfo=timezone.utc)
        stamp = float(moment.timestamp())
        parents = [item.encode("ascii") for item in (extra_parents or [])]
        # sign=False: a machine gitconfig with commit.gpgsign would import gpg and fail.
        sha = repo.get_worktree().commit(
            message=_commit_message(note, shop_id, station),
            author=author,
            committer=author,
            author_timestamp=stamp,
            commit_timestamp=stamp,
            author_timezone=0,
            commit_timezone=0,
            merge_heads=parents or None,
            no_verify=True,
            sign=False,
        )
        return sha.decode("ascii")

    def history(
        self,
        path: Optional[str] = None,
        query: str = "",
        offset: int = 0,
        limit: int = 200,
        all_lines: bool = False,
    ) -> List[Change]:
        if not self.exists() or self.head_sha() is None:
            return []
        milestones = self._milestones()
        selected = self._select_commits(path, query, offset, limit, all_lines)
        return [
            self._change(sha, milestones, line, with_files=False)
            for sha, line in selected
        ]

    def change(self, sha: str) -> Change:
        return self._change(sha, self._milestones(), self.branch_name())

    def diff_commits(self, new_sha: str, old_sha: Optional[str] = None) -> List[FileDiff]:
        new_commit = self._as_commit(new_sha)
        old_tree = None
        if old_sha:
            old_tree = self._as_commit(old_sha).tree
        elif new_commit.parents:
            old_tree = self._as_commit(new_commit.parents[0].decode("ascii")).tree
        return self._diff_trees(old_tree, new_commit.tree)

    def working_diff(self, path: str) -> FileDiff:
        head = self.head_sha()
        old = self.file_bytes(head, path) if head else None
        new = self._read_work(path)
        diff = _file_diff(path, old, new)
        if diff is None:
            return FileDiff(path, FILE_MODIFIED, ())
        return diff

    def blame(self, path: str) -> List[BlameLine]:
        head = self.head_sha()
        if head is None:
            return []
        key = (path, head)
        cached = self._blame_cache.get(key)
        if cached is not None:
            return cached
        if self.file_bytes(head, path) is None:
            self._blame_cache[key] = []
            return []
        try:
            rows = annotate(self.root, path)
        except (KeyError, ValueError):
            self._blame_cache[key] = []
            return []
        lines: List[BlameLine] = []
        for number, row in enumerate(rows, start=1):
            commit = row[0][0]
            note, shop, _station = _split_message(commit.message or b"")
            author_name, _email = _split_author(commit.author or b"")
            lines.append(
                BlameLine(
                    line=number,
                    change_id=commit.id.decode("ascii"),
                    author_id=shop,
                    author_name=author_name,
                    when=datetime.fromtimestamp(int(commit.author_time or 0), timezone.utc),
                    note=note,
                )
            )
        self._blame_cache[key] = lines
        return lines

    def file_bytes(self, sha: Optional[str], path: str) -> Optional[bytes]:
        if not sha:
            return None
        commit = self._as_commit(sha)
        try:
            _mode, blob_sha = self._lookup(commit.tree, path)
        except KeyError:
            return None
        blob = self._repo().object_store[blob_sha]
        if not isinstance(blob, Blob):
            return None
        return bytes(blob.data)

    def tree_files(self, sha: Optional[str]) -> Dict[str, bytes]:
        if not sha:
            return {}
        commit = self._as_commit(sha)
        store = self._repo().object_store
        files: Dict[str, bytes] = {}
        for entry in iter_tree_contents(store, commit.tree):
            if entry.path is None or entry.mode is None or entry.sha is None:
                continue
            if not stat.S_ISREG(entry.mode):
                continue
            blob = store[entry.sha]
            if isinstance(blob, Blob):
                files[entry.path.decode("utf-8")] = bytes(blob.data)
        return files

    def has_object(self, sha: str) -> bool:
        if not sha or not self.exists():
            return False
        try:
            self._repo().object_store[sha.encode("ascii")]
        except (KeyError, ValueError):
            return False
        return True

    def merge_base(self, left: str, right: str) -> Optional[str]:
        if not left or not right:
            return None
        if left == right:
            return left
        try:
            found = find_merge_base(
                self._repo(),
                [left.encode("ascii"), right.encode("ascii")],
            )
        except (KeyError, ValueError):
            return None
        if not found:
            return None
        first = found[0]
        if isinstance(first, bytes):
            return first.decode("ascii")
        return str(first)

    def commit_time(self, sha: str) -> int:
        return int(self._as_commit(sha).commit_time or 0)

    def store_blob(self, data: bytes) -> str:
        blob = Blob.from_string(data)
        self._repo().object_store.add_object(blob)
        return blob.id.decode("ascii")

    def read_blob(self, sha: str) -> bytes:
        try:
            obj = self._repo().object_store[sha.encode("ascii")]
        except KeyError as exc:
            raise TeamSyncError("That combine blob is missing.") from exc
        if not isinstance(obj, Blob):
            raise TeamSyncError("That combine blob is missing.")
        return bytes(obj.data)

    def tree_modes(self, sha: Optional[str]) -> Dict[str, int]:
        if not sha:
            return {}
        found: Dict[str, int] = {}
        commit = self._as_commit(sha)
        for entry in iter_tree_contents(self._repo().object_store, commit.tree):
            if entry.path is None or entry.mode is None or not stat.S_ISREG(entry.mode):
                continue
            found[entry.path.decode("utf-8", "surrogateescape")] = int(entry.mode)
        return found

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        return self.merge_base(ancestor, descendant) == ancestor

    def count_since(self, tip: str, stops: Sequence[str]) -> int:
        stop = set(stops)
        seen = set()

        def visit(sha: str) -> int:
            if not sha or sha in seen or sha in stop:
                return 0
            seen.add(sha)
            total = 1
            for parent in self._parents(sha):
                total += visit(parent)
            return total

        return visit(tip)

    def new_commit_ids(self, tip: str, have_sha: Optional[str]) -> List[str]:
        have = set(self._ancestor_set(have_sha)) if have_sha else set()
        ordered: List[str] = []
        seen = set()

        def visit(sha: str) -> None:
            if not sha or sha in seen or sha in have:
                return
            seen.add(sha)
            for parent in self._parents(sha):
                visit(parent)
            ordered.append(sha)

        visit(tip)
        return ordered

    def checkout(self, sha: str, branch: Optional[str] = None) -> None:
        repo = self._repo()
        commit = self._as_commit(sha)
        old_tree = None
        head = self.head_sha()
        if head:
            old_tree = self._as_commit(head).tree
        self._assert_tree_paths(commit.tree)
        changes = tree_changes(repo.object_store, old_tree, commit.tree)
        try:
            update_working_tree(
                repo,
                old_tree,
                commit.tree,
                changes,
                allow_overwrite_modified=False,
            )
            self._checkout_paths_dulwich_skips(old_tree, commit.tree)
        except OSError as exc:
            raise TeamSyncError(
                "Could not check out that change without overwriting files."
            ) from exc
        if branch:
            ref = b"refs/heads/" + branch.encode("utf-8")
            repo.refs[ref] = commit.id
            repo.refs.set_symbolic_ref(b"HEAD", ref)
        else:
            repo.refs[b"HEAD"] = commit.id

    def create_branch(self, name: str, sha: str) -> None:
        self._repo().refs[b"refs/heads/" + name.encode("utf-8")] = sha.encode("ascii")

    def delete_branch(self, name: str) -> None:
        if self.branch_name() == name:
            raise TeamSyncError("Switch back to main before deleting this line.")
        ref = b"refs/heads/" + name.encode("utf-8")
        try:
            del self._repo().refs[ref]
        except KeyError as exc:
            raise TeamSyncError(f"There is no line named {name}.") from exc

    def switch(self, line: str) -> None:
        if self.dirty():
            raise TeamSyncError("Set this work aside before switching lines.")
        ref = b"refs/heads/" + line.encode("utf-8")
        try:
            sha = self._repo().refs[ref].decode("ascii")
        except KeyError as exc:
            raise TeamSyncError(f"There is no line named {line}.") from exc
        self.checkout(sha, line)

    def tag(self, sha: str, version: str, note: str, author_name: str, author_email: str, when: datetime) -> None:
        name = version if version.startswith("v") else f"v{version}"
        commit = self._as_commit(sha)
        tag = Tag()
        tag.object = (Commit, commit.id)
        tag.name = name.encode("utf-8")
        tag.tagger = f"{author_name} <{author_email}>".encode("utf-8")
        moment = when if when.tzinfo is not None else when.replace(tzinfo=timezone.utc)
        tag.tag_time = int(moment.timestamp())
        tag.tag_timezone = 0
        tag.message = (note or name).encode("utf-8") + b"\n"
        self._repo().object_store.add_object(tag)
        self._repo().refs[b"refs/tags/" + tag.name] = tag.id

    def set_ref(self, name: str, sha: str) -> None:
        self._repo().refs[name.encode("utf-8")] = sha.encode("ascii")

    def get_ref(self, name: str) -> Optional[str]:
        if not self.exists():
            return None
        try:
            return self._repo().refs[name.encode("utf-8")].decode("ascii")
        except KeyError:
            return None

    def delete_ref(self, name: str) -> None:
        if not self.exists():
            return
        try:
            del self._repo().refs[name.encode("utf-8")]
        except KeyError:
            return

    def create_bundle(self, ref: str, prerequisites: Sequence[str]) -> bytes:
        from dulwich.bundle import create_bundle_from_repo, write_bundle

        ref_name = ref if ref.startswith("refs/") else f"refs/heads/{ref}"
        prereq = [item.encode("ascii") for item in prerequisites if item]
        bundle = create_bundle_from_repo(
            self._repo(),
            refs=[ref_name.encode("utf-8")],
            prerequisites=prereq,
        )
        buffer = io.BytesIO()
        write_bundle(buffer, bundle)
        return buffer.getvalue()

    def import_pack(self, bundle: bytes) -> Dict[str, str]:
        """Read a bundle. Refs are not moved; the caller does that after this returns.

        Real git's offset deltas survive only through add_thin_pack. Bundle.store_objects
        and add_pack_data(iter_unpacked()) drop those commits, so this path does not use them.
        """

        if b"\n\n" not in bundle:
            raise TeamSyncError("The bundle is incomplete.")
        header, pack = bundle.split(b"\n\n", 1)
        refs: Dict[str, str] = {}
        for line in header.split(b"\n")[1:]:
            if not line or line.startswith(b"-") or line.startswith(b"#") or line.startswith(b"@"):
                continue
            try:
                sha, refname = line.split(b" ", 1)
            except ValueError:
                continue
            refs[refname.decode("utf-8")] = sha.decode("ascii")
        existing = set(self._repo().object_store)
        stream = io.BytesIO(pack)
        try:
            self._repo().object_store.add_thin_pack(stream.read, None)
        except Exception as exc:
            raise TeamSyncError(f"The bundle is damaged: {exc}") from exc
        self._verify_closure(list(refs.values()), existing)
        return refs

    def set_aside(self, name: str, author_name: str, author_email: str) -> None:
        if not self.dirty():
            raise TeamSyncError("Nothing to set aside.")
        author = f"{author_name} <{author_email}>".encode("utf-8")
        Stash.from_repo(self._repo()).push(
            message=name.encode("utf-8"),
            author=author,
            committer=author,
        )

    def aside_entries(self) -> List[SetAside]:
        if not self.exists():
            return []
        stash = Stash.from_repo(self._repo())
        entries: List[SetAside] = []
        for index, entry in enumerate(stash.stashes()):
            commit = self._repo().object_store[entry.new_sha]
            if not isinstance(commit, Commit) or not commit.parents:
                continue
            parent = self._repo().object_store[commit.parents[0]]
            if not isinstance(parent, Commit):
                continue
            files = list(tree_changes(self._repo().object_store, parent.tree, commit.tree))
            message = _stash_name(entry.message)
            entries.append(
                SetAside(
                    index=index,
                    name=message,
                    when=datetime.fromtimestamp(int(entry.timestamp), timezone.utc),
                    files=len(files),
                )
            )
        return entries

    def aside_trees(self, index: int) -> Tuple[str, str, str]:
        """Return stash sha, base sha, and the name."""

        stash = Stash.from_repo(self._repo())
        try:
            entry = stash.stashes()[index]
        except IndexError as exc:
            raise TeamSyncError("That set-aside is gone.") from exc
        commit = self._repo().object_store[entry.new_sha]
        if not isinstance(commit, Commit) or not commit.parents:
            raise TeamSyncError("That set-aside is damaged.")
        return (
            commit.id.decode("ascii"),
            commit.parents[0].decode("ascii"),
            _stash_name(entry.message),
        )

    def drop_aside(self, index: int) -> None:
        Stash.from_repo(self._repo()).drop(index)

    def replace_worktree(
        self,
        files: Dict[str, Optional[bytes]],
        modes: Optional[Dict[str, int]] = None,
        *,
        only_listed: bool = False,
    ) -> None:
        root = Path(self.root)
        file_modes = modes or {}
        for path in files:
            _guard_rel(path)
        keep = {path for path, data in files.items() if data is not None}
        for path, data in files.items():
            target = _work_target(root, path)
            if data is None:
                if target.is_file() and not target.is_symlink():
                    target.unlink()
                continue
            if target.is_file() and not target.is_symlink() and target.read_bytes() == data:
                _apply_mode(target, file_modes.get(path, 0o100644))
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_bytes(target, data)
            _apply_mode(target, file_modes.get(path, 0o100644))
        if only_listed:
            return
        for rel in self._tree_shas(self.head_sha()):
            if rel in keep:
                continue
            _guard_rel(rel)
            target = _work_target(root, rel)
            if target.is_file() and not target.is_symlink():
                target.unlink()

    def _repo(self) -> Repo:
        if not self.exists():
            raise TeamSyncError("Share the project before using its history.")
        if self._cached is None:
            self._cached = Repo(self.root)
            config = self._cached.get_config()
            config.set((b"commit",), b"gpgsign", b"false")
            config.write_to_path()
        return self._cached

    def _as_commit(self, sha: str) -> Commit:
        obj = self._repo().object_store[sha.encode("ascii")]
        if not isinstance(obj, Commit):
            raise TeamSyncError("That change is not a commit.")
        return obj

    def _parents(self, sha: str) -> List[str]:
        try:
            commit = self._as_commit(sha)
        except (KeyError, TeamSyncError, ValueError):
            return []
        return [parent.decode("ascii") for parent in commit.parents]

    def _ancestor_set(self, sha: str) -> set:
        seen = set()
        stack = [sha]
        while stack:
            current = stack.pop()
            if not current or current in seen:
                continue
            seen.add(current)
            stack.extend(self._parents(current))
        return seen

    def _lookup(self, tree_sha: bytes, path: str) -> Tuple[int, bytes]:
        tree = self._repo().object_store[tree_sha]
        return tree.lookup_path(self._repo().object_store.__getitem__, path.encode("utf-8"))

    def _tree_shas(self, sha: Optional[str]) -> Dict[str, bytes]:
        if not sha:
            return {}
        commit = self._as_commit(sha)
        found: Dict[str, bytes] = {}
        for entry in iter_tree_contents(self._repo().object_store, commit.tree):
            if entry.path is None or entry.mode is None or entry.sha is None:
                continue
            if not stat.S_ISREG(entry.mode):
                continue
            found[entry.path.decode("utf-8")] = entry.sha
        return found

    def _work_sha(self, index: object, rel: str) -> bytes:
        full = os.path.join(self.root, rel)
        st = os.lstat(full)
        key = rel.encode("utf-8")
        entry = index[key] if key in index else None  # type: ignore[index]
        if entry is not None and not isinstance(entry, ConflictedIndexEntry) and _stat_matches(entry, st):
            return entry.sha
        with open(full, "rb") as handle:
            blob = Blob()
            blob.data = handle.read()
            return blob.id

    def _iter_work_files(self) -> Iterable[str]:
        ignore = self._ignore()
        for dirpath, dirnames, filenames in os.walk(self.root):
            rel_dir = os.path.relpath(dirpath, self.root)
            if rel_dir == ".":
                rel_dir = ""
            kept = []
            for name in dirnames:
                if name == ".git":
                    continue
                rel = f"{rel_dir}/{name}" if rel_dir else name
                if ignore.is_ignored(rel + "/") is True:
                    continue
                kept.append(name)
            dirnames[:] = kept
            for name in filenames:
                rel = f"{rel_dir}/{name}" if rel_dir else name
                if ignore.is_ignored(rel) is True:
                    continue
                full = os.path.join(dirpath, name)
                if os.path.isfile(full) and not os.path.islink(full):
                    yield rel.replace(os.sep, "/")

    def _ignore(self) -> IgnoreFilterManager:
        path = os.path.join(self.root, ".gitignore")
        try:
            mtime = os.stat(path).st_mtime_ns
        except OSError:
            mtime = 0
        if self._ignore_mgr is None or self._ignore_key != mtime:
            self._ignore_mgr = IgnoreFilterManager.from_repo(self._repo())
            self._ignore_key = mtime
        return self._ignore_mgr

    def work_bytes(self, path: str) -> Optional[bytes]:
        _guard_rel(path)
        return self._read_work(path)

    def _read_work(self, path: str) -> Optional[bytes]:
        full = Path(self.root).joinpath(*path.split("/"))
        if not full.is_file():
            return None
        return full.read_bytes()

    def _diff_trees(self, old_tree: Optional[bytes], new_tree: bytes) -> List[FileDiff]:
        diffs: List[FileDiff] = []
        store = self._repo().object_store
        for change in tree_changes(store, old_tree, new_tree):
            if change.type == "add" and change.new is not None and change.new.path and change.new.sha:
                data = _blob_bytes(store, change.new.sha)
                diff = _file_diff(change.new.path.decode("utf-8"), None, data)
            elif change.type == "delete" and change.old is not None and change.old.path and change.old.sha:
                data = _blob_bytes(store, change.old.sha)
                diff = _file_diff(change.old.path.decode("utf-8"), data, None)
            elif change.type == "modify" and change.new is not None and change.old is not None:
                if not change.new.path or not change.new.sha or not change.old.sha:
                    continue
                diff = _file_diff(
                    change.new.path.decode("utf-8"),
                    _blob_bytes(store, change.old.sha),
                    _blob_bytes(store, change.new.sha),
                )
            else:
                continue
            if diff is not None:
                diffs.append(diff)
        return diffs

    def _select_commits(
        self,
        path: Optional[str],
        query: str,
        offset: int,
        limit: int,
        all_lines: bool,
    ) -> List[Tuple[str, str]]:
        include: List[Tuple[str, str]] = []
        if all_lines:
            for name in self.branch_names():
                sha = self.get_ref(f"refs/heads/{name}")
                if sha:
                    include.append((sha, name))
        else:
            head = self.head_sha()
            if head:
                include.append((head, self.branch_name()))
        if not include:
            return []
        walker = self._repo().get_walker(
            include=[sha.encode("ascii") for sha, _line in include],
            paths=[path.encode("utf-8")] if path else None,
        )
        line_for = {sha: line for sha, line in include}
        matched: List[Tuple[str, str]] = []
        needle = query.lower()
        for entry in walker:
            commit = entry.commit
            sha = commit.id.decode("ascii")
            if needle:
                note, _shop, _station = _split_message(commit.message or b"")
                author_name, _email = _split_author(commit.author or b"")
                if needle not in note.lower() and needle not in author_name.lower():
                    continue
            matched.append((sha, line_for.get(sha, self.branch_name())))
            if not needle and len(matched) >= offset + limit:
                break
        # Walker yields newest first. Commits reached only through another tip
        # keep the current line label when they are also on it.
        return matched[offset : offset + limit]

    def changed_files(self, sha: str) -> List[FileChange]:
        """Names and kinds for one commit. Callers that list history skip this."""
        commit = self._as_commit(sha)
        parent_tree = None
        if commit.parents:
            parent_tree = self._as_commit(commit.parents[0].decode("ascii")).tree
        return self._changed_files(parent_tree, commit.tree)

    def _change(
        self,
        sha: str,
        milestones: Dict[str, str],
        line: str,
        *,
        with_files: bool = True,
    ) -> Change:
        commit = self._as_commit(sha)
        note, shop, _station = _split_message(commit.message or b"")
        author_name, _email = _split_author(commit.author or b"")
        files = self.changed_files(sha) if with_files else []
        return Change(
            id=sha,
            parents=tuple(parent.decode("ascii") for parent in commit.parents),
            author_id=shop,
            author_name=author_name,
            when=datetime.fromtimestamp(int(commit.author_time or 0), timezone.utc),
            note=note,
            files=tuple(files),
            milestone=milestones.get(sha),
            line=line,
        )

    def _milestones(self) -> Dict[str, str]:
        if not self.exists():
            return {}
        found: Dict[str, str] = {}
        repo = self._repo()
        for ref in repo.refs.allkeys():
            if not ref.startswith(b"refs/tags/"):
                continue
            name = ref[len(b"refs/tags/") :].decode("utf-8")
            try:
                sha = repo.refs[ref]
                obj = repo.object_store[sha]
            except KeyError:
                continue
            if isinstance(obj, Tag):
                _kind, target = obj.object
                sha = target
            version = name[1:] if name.startswith("v") else name
            found[sha.decode("ascii")] = version
        return found

    def _checkout_paths_dulwich_skips(
        self,
        old_tree: Optional[bytes],
        new_tree: bytes,
    ) -> None:
        """dulwich 0.24 skips every path that starts with ``.git``.

        That includes ``.gitignore``. The file never reaches the disk or the
        index, so the next commit drops it from the project.
        """
        repo = self._repo()
        store = repo.object_store
        old_files = _regular_tree_files(store, old_tree)
        new_files = _regular_tree_files(store, new_tree)
        index = repo.open_index()
        touched = False
        for rel, (raw_path, blob_id) in new_files.items():
            if not _skipped_dotgit_file(rel):
                continue
            _guard_rel(rel)
            full = os.path.join(self.root, *rel.split("/"))
            parent = os.path.dirname(full)
            if parent:
                os.makedirs(parent, exist_ok=True)
            data = _blob_bytes(store, blob_id)
            if os.path.lexists(full):
                if os.path.islink(full) or not os.path.isfile(full):
                    raise OSError(f"Cannot replace {rel} with the shared file.")
                with open(full, "rb") as handle:
                    current = handle.read()
                previous_id = old_files.get(rel, (b"", b""))[1]
                if current != data:
                    if not previous_id or current != _blob_bytes(store, previous_id):
                        raise OSError(f"Local changes to {rel} would be overwritten.")
                    with open(full, "wb") as handle:
                        handle.write(data)
            else:
                with open(full, "wb") as handle:
                    handle.write(data)
            index[raw_path] = index_entry_from_stat(os.lstat(full), blob_id)
            touched = True
        for rel, (raw_path, blob_id) in old_files.items():
            if rel in new_files or not _skipped_dotgit_file(rel):
                continue
            _guard_rel(rel)
            full = os.path.join(self.root, *rel.split("/"))
            if os.path.lexists(full):
                if os.path.islink(full) or not os.path.isfile(full):
                    raise OSError(f"Cannot remove {rel}.")
                with open(full, "rb") as handle:
                    current = handle.read()
                if current != _blob_bytes(store, blob_id):
                    raise OSError(f"Local changes to {rel} would be overwritten.")
                os.remove(full)
            try:
                del index[raw_path]
            except KeyError:
                pass
            touched = True
        if touched:
            index.write()

    def _assert_tree_paths(self, tree_sha: bytes) -> None:
        for entry in iter_tree_contents(self._repo().object_store, tree_sha):
            if entry.path is None:
                continue
            _guard_rel(entry.path.decode("utf-8", "surrogateescape"))

    def _changed_files(self, old_tree: Optional[bytes], new_tree: bytes) -> List[FileChange]:
        """Names and kinds only. Blob bytes and line diffs stay in ``diff_commits``."""

        files: List[FileChange] = []
        for change in tree_changes(self._repo().object_store, old_tree, new_tree):
            if change.type == "delete" and change.old is not None and change.old.path:
                files.append(
                    FileChange(change.old.path.decode("utf-8", "surrogateescape"), FILE_DELETED)
                )
            elif change.type == "add" and change.new is not None and change.new.path:
                files.append(
                    FileChange(change.new.path.decode("utf-8", "surrogateescape"), FILE_ADDED)
                )
            elif change.new is not None and change.new.path:
                files.append(
                    FileChange(change.new.path.decode("utf-8", "surrogateescape"), FILE_MODIFIED)
                )
        return files

    def _verify_closure(self, tips: Sequence[str], existing: Optional[set] = None) -> None:
        store = self._repo().object_store
        seen = set()
        stop = existing or set()
        stack = [tip.encode("ascii") for tip in tips if tip]
        while stack:
            sha = stack.pop()
            if sha in seen or sha in stop:
                continue
            seen.add(sha)
            try:
                obj = store[sha]
            except KeyError as exc:
                raise TeamSyncError("The bundle is missing an object it claims to contain.") from exc
            if isinstance(obj, Commit):
                stack.append(obj.tree)
                stack.extend(obj.parents)
            elif obj.type_name == b"tree":
                for entry in obj.iteritems():  # type: ignore[attr-defined]
                    if entry.sha is not None:
                        stack.append(entry.sha)
            elif isinstance(obj, Tag):
                _kind, target = obj.object
                stack.append(target)
            elif isinstance(obj, Blob):
                continue
            else:
                raise TeamSyncError("The bundle contains an object Team Sync does not accept.")


def _skipped_dotgit_file(rel: str) -> bool:
    """True for names dulwich drops, and false for the ``.git`` directory itself."""
    if rel == ".git" or rel.startswith(".git/"):
        return False
    return rel.startswith(".git")


def _regular_tree_files(store: object, tree_sha: Optional[bytes]) -> Dict[str, Tuple[bytes, bytes]]:
    if not tree_sha:
        return {}
    found: Dict[str, Tuple[bytes, bytes]] = {}
    for entry in iter_tree_contents(store, tree_sha):  # type: ignore[arg-type]
        if entry.path is None or entry.sha is None or entry.mode is None:
            continue
        if not stat.S_ISREG(entry.mode):
            continue
        found[entry.path.decode("utf-8", "surrogateescape")] = (entry.path, entry.sha)
    return found


def _guard_rel(path: str) -> str:
    if not path or path.startswith("/") or path.startswith("\\") or "\\" in path:
        raise TeamSyncError(f"Refusing to write {path}.")
    for part in path.split("/"):
        if part in {"", ".", ".."} or part.lower() == ".git":
            raise TeamSyncError(f"Refusing to write {path}.")
    return path


def _work_target(root: Path, path: str) -> Path:
    target = root.joinpath(*_guard_rel(path).split("/"))
    try:
        target.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise TeamSyncError(f"Refusing to write {path}.") from exc
    return target


def _apply_mode(path: Path, mode: int) -> None:
    os.chmod(path, 0o755 if mode & 0o111 else 0o644)


def _stash_name(message: object) -> str:
    text = message.decode("utf-8", "replace") if isinstance(message, bytes) else str(message)
    text = text.strip()
    if text.startswith("commit: "):
        text = text[len("commit: ") :].strip()
    return text or "Set aside"


def _commit_message(note: str, shop_id: str, station: str) -> bytes:
    text = note.rstrip() + f"\n\n{_AUTHOR_TRAILER}{shop_id}\n{_STATION_TRAILER}{station}\n"
    return text.encode("utf-8")


def _split_message(message: bytes) -> Tuple[str, str, str]:
    text = message.decode("utf-8", "replace")
    shop = ""
    station = ""
    lines = []
    for line in text.splitlines():
        if line.startswith(_AUTHOR_TRAILER):
            shop = line[len(_AUTHOR_TRAILER) :].strip()
        elif line.startswith(_STATION_TRAILER):
            station = line[len(_STATION_TRAILER) :].strip()
        else:
            lines.append(line)
    return "\n".join(lines).strip(), shop, station


def _split_author(author: bytes) -> Tuple[str, str]:
    text = author.decode("utf-8", "replace")
    if "<" in text and text.endswith(">"):
        name, email = text.rsplit("<", 1)
        return name.strip(), email[:-1].strip()
    return text.strip(), ""


def _stat_matches(entry: object, st: os.stat_result) -> bool:
    size = getattr(entry, "size", None)
    mtime = getattr(entry, "mtime", None)
    dev = getattr(entry, "dev", None)
    ino = getattr(entry, "ino", None)
    if size != st.st_size or int(dev) != int(st.st_dev) or int(ino) != int(st.st_ino):
        return False
    if isinstance(mtime, tuple):
        nsec = int(getattr(st, "st_mtime_ns", 0)) % 1_000_000_000
        return int(mtime[0]) == int(st.st_mtime) and int(mtime[1]) == nsec
    return int(mtime) == int(st.st_mtime)


def _blob_bytes(store: object, sha: bytes) -> bytes:
    blob = store[sha]  # type: ignore[index]
    if isinstance(blob, Blob):
        return bytes(blob.data)
    return b""


def _file_diff(path: str, old: Optional[bytes], new: Optional[bytes]) -> Optional[FileDiff]:
    if old is None and new is None:
        return None
    if old is None:
        kind = FILE_ADDED
    elif new is None:
        kind = FILE_DELETED
    else:
        kind = FILE_MODIFIED
    form = path.lower().endswith(".ui")
    binary = is_binary_payload(old) or is_binary_payload(new)
    if (old is not None and len(old) > WHOLE_FILE_BYTES) or (new is not None and len(new) > WHOLE_FILE_BYTES):
        binary = True
    if binary and not form:
        return FileDiff(path, kind, (), False, True)
    old_lines = inspect_text(old)[0] if old is not None else ()
    new_lines = inspect_text(new)[0] if new is not None else ()
    old_text = old.decode("utf-8", "replace") if form and old is not None else None
    new_text = new.decode("utf-8", "replace") if form and new is not None else None
    return FileDiff(
        path,
        kind,
        diff_hunks(old_lines, new_lines),
        form,
        False,
        old_text,
        new_text,
    )
