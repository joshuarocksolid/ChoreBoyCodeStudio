"""Stage Linux tree-sitter wheels into a ChoreBoy product payload.

The shop runtime is FreeCAD's CPython 3.9.2 on Linux x86-64. A Mac vendor
tree stores grammar bindings under the same ``_binding.abi3.so`` name as the
Linux wheels, so filename checks cannot tell them apart. These helpers
download the manylinux wheels named by ``TREE_SITTER_WHEEL_PINS`` and overlay
the Linux binaries onto the staged payload.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import shutil
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

from app.treesitter.language_specs import LANGUAGE_SPECS

CP39_TREE_SITTER_PYTHON_VERSION = "3.9"
CP39_TREE_SITTER_PLATFORM = "manylinux_2_17_x86_64"
CP39_TREE_SITTER_SOABI = "cpython-39-x86_64-linux-gnu"
GRAMMAR_BINDING_FILENAME = "_binding.abi3.so"

# tree-sitter 0.23.2 parser_set_language rejects language ABI values outside
# this range. The shipped core binding encodes the bounds as immediate
# operands (13 and 14). Update both numbers when the core pin changes.
CORE_LANGUAGE_ABI_MIN = 13
CORE_LANGUAGE_ABI_MAX = 14

_EXPLICIT_ABI_EXCLUSIONS = {
    "tree_sitter_sql": (
        "SQL files stay plain text. "
        "The editor still ignores an incompatible SQL grammar at runtime."
    ),
}

_SHT_SYMTAB = 2
_STT_OBJECT = 1
_PT_LOAD = 1


def tree_sitter_core_binding_name(soabi: str) -> str:
    """Return the tree-sitter core ``_binding`` filename for *soabi*."""
    return f"_binding.{soabi}.so"


@dataclass(frozen=True)
class TreeSitterWheelPin:
    """One manylinux wheel the product build overlays onto the staged vendor tree."""

    package_name: str
    version: str
    binding_filename: str
    pip_abi: str = ""

    @property
    def distribution(self) -> str:
        return self.package_name.replace("_", "-")

    @property
    def requirement(self) -> str:
        return f"{self.distribution}=={self.version}"

    @property
    def wheel_member(self) -> str:
        return f"{self.package_name}/{self.binding_filename}"


@dataclass(frozen=True)
class GrammarExclusion:
    package_name: str
    language_abi: int
    reason: str


@dataclass(frozen=True)
class GrammarStageResult:
    overlaid: tuple[Path, ...]
    exclusions: tuple[GrammarExclusion, ...]


def _core_pin() -> TreeSitterWheelPin:
    return TreeSitterWheelPin(
        package_name="tree_sitter",
        version="0.23.2",
        binding_filename=tree_sitter_core_binding_name(CP39_TREE_SITTER_SOABI),
        pip_abi="cp39",
    )


def _grammar_pin(package_name: str, version: str) -> TreeSitterWheelPin:
    return TreeSitterWheelPin(
        package_name=package_name,
        version=version,
        binding_filename=GRAMMAR_BINDING_FILENAME,
    )


# Versions live here. setup_vendor_py39.sh and setup_vendor_py311.sh read this
# table. Package names must match app.treesitter.language_specs.
_GRAMMAR_VERSIONS = (
    ("tree_sitter_python", "0.23.6"),
    ("tree_sitter_json", "0.24.8"),
    ("tree_sitter_html", "0.23.2"),
    ("tree_sitter_xml", "0.7.0"),
    ("tree_sitter_css", "0.23.2"),
    ("tree_sitter_bash", "0.23.3"),
    ("tree_sitter_markdown", "0.3.2"),
    ("tree_sitter_yaml", "0.7.0"),
    ("tree_sitter_toml", "0.7.0"),
    ("tree_sitter_javascript", "0.23.1"),
    ("tree_sitter_sql", "0.3.9"),
)

TREE_SITTER_WHEEL_PINS: tuple[TreeSitterWheelPin, ...] = (_core_pin(),) + tuple(
    _grammar_pin(package_name, version) for package_name, version in _GRAMMAR_VERSIONS
)

CORE_WHEEL_PIN = TREE_SITTER_WHEEL_PINS[0]
CP39_TREE_SITTER_VERSION = CORE_WHEEL_PIN.version
CP39_TREE_SITTER_BINDING_NAME = CORE_WHEEL_PIN.binding_filename

_INCOMPATIBLE_BINDING_RE = re.compile(
    r"^_binding\.cpython-3\d+-x86_64-linux-gnu\.so$"
)


def iter_pip_requirements() -> tuple[str, ...]:
    """Return ``distribution==version`` pins for every shipped tree-sitter wheel."""
    return tuple(pin.requirement for pin in TREE_SITTER_WHEEL_PINS)


def grammar_wheel_pins() -> tuple[TreeSitterWheelPin, ...]:
    """Return grammar pins in language-spec order.

    Raises ``RuntimeError`` when a default language has no pin, or a pin has
    no default language. ``json`` and ``jsonc`` share one package.
    """
    included: list[str] = []
    seen: set[str] = set()
    for spec in LANGUAGE_SPECS:
        if not spec.included_by_default or spec.package_name in seen:
            continue
        seen.add(spec.package_name)
        included.append(spec.package_name)
    pins = {
        pin.package_name: pin
        for pin in TREE_SITTER_WHEEL_PINS
        if pin.package_name != CORE_WHEEL_PIN.package_name
    }
    missing = [name for name in included if name not in pins]
    extra = [name for name in pins if name not in seen]
    if missing or extra:
        raise RuntimeError(
            "tree-sitter grammar pins do not match language specs. "
            f"missing pins: {', '.join(missing) or 'none'}. "
            f"pins without a language spec: {', '.join(extra) or 'none'}."
        )
    return tuple(pins[name] for name in included)


def _wheel_name_re(pin: TreeSitterWheelPin) -> re.Pattern[str]:
    return re.compile(
        r"^"
        + re.escape(pin.package_name)
        + r"-"
        + re.escape(pin.version)
        + r"-cp3\d+-.*manylinux.*\.whl$"
    )


def _find_cached_wheel(cache_dir: Path, pin: TreeSitterWheelPin) -> Path | None:
    if not cache_dir.is_dir():
        return None
    pattern = _wheel_name_re(pin)
    for entry in sorted(cache_dir.iterdir()):
        if entry.is_file() and pattern.match(entry.name):
            return entry
    return None


def _pip_download_command(pin: TreeSitterWheelPin, cache_dir: Path) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "pip",
        "download",
        pin.requirement,
        "--no-deps",
        "--only-binary=:all:",
        f"--python-version={CP39_TREE_SITTER_PYTHON_VERSION}",
        f"--platform={CP39_TREE_SITTER_PLATFORM}",
        "--implementation=cp",
    ]
    if pin.pip_abi:
        command.append(f"--abi={pin.pip_abi}")
    command.extend(["--dest", str(cache_dir)])
    return command


def download_tree_sitter_wheel(pin: TreeSitterWheelPin, cache_dir: Path) -> Path:
    """Return a cached or freshly downloaded manylinux wheel for *pin*."""
    cached = _find_cached_wheel(cache_dir, pin)
    if cached is not None:
        return cached

    cache_dir.mkdir(parents=True, exist_ok=True)
    command = _pip_download_command(pin, cache_dir)
    try:
        result = subprocess.run(command, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "pip is not available to download the "
            f"{pin.requirement} wheel. Install pip or pre-populate {cache_dir} "
            f"with a {pin.package_name}-{pin.version}-cp3*-manylinux*.whl file."
        ) from exc
    if result.returncode != 0:
        raise RuntimeError(
            "pip download failed while fetching the "
            f"{pin.requirement} wheel (exit {result.returncode}). "
            f"Pre-populate {cache_dir} with a matching manylinux wheel to build offline.\n"
            f"stdout: {result.stdout.strip()}\n"
            f"stderr: {result.stderr.strip()}"
        )

    wheel = _find_cached_wheel(cache_dir, pin)
    if wheel is None:
        raise RuntimeError(
            "pip download completed but no matching manylinux wheel for "
            f"{pin.requirement} was found in {cache_dir}"
        )
    return wheel


def download_cp39_tree_sitter_wheel(cache_dir: Path) -> Path:
    """Return a path to a cp39 manylinux ``tree-sitter`` wheel."""
    return download_tree_sitter_wheel(CORE_WHEEL_PIN, cache_dir)


def _remove_incompatible_bindings(staged_tree_sitter_dir: Path) -> None:
    for entry in staged_tree_sitter_dir.iterdir():
        if entry.is_file() and _INCOMPATIBLE_BINDING_RE.match(entry.name):
            if entry.name == CP39_TREE_SITTER_BINDING_NAME:
                continue
            entry.unlink()


def _remove_other_bindings(package_dir: Path, keep_name: str) -> None:
    for entry in package_dir.glob("_binding*.so"):
        if entry.is_file() and entry.name != keep_name:
            entry.unlink()


def _extract_binding(wheel_path: Path, member_name: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(wheel_path) as wheel:
        try:
            info = wheel.getinfo(member_name)
        except KeyError as exc:
            raise RuntimeError(
                f"tree-sitter wheel {wheel_path.name} is missing {member_name}"
            ) from exc
        with wheel.open(info) as source, destination.open("wb") as target:
            target.write(source.read())
    return destination


def stage_cp39_tree_sitter_core_binding(
    staged_tree_sitter_dir: Path,
    cache_dir: Path,
) -> Path:
    """Overlay the cp39 ``_binding`` onto a staged ``tree_sitter`` package.

    Removes any sibling ``_binding.cpython-3*-x86_64-linux-gnu.so`` files so
    the packaging validator sees a single, correct binding. Returns the path
    to the staged cp39 binding.
    """
    if not staged_tree_sitter_dir.is_dir():
        raise RuntimeError(
            f"staged tree_sitter directory not found: {staged_tree_sitter_dir}"
        )
    wheel_path = download_cp39_tree_sitter_wheel(cache_dir)
    _remove_incompatible_bindings(staged_tree_sitter_dir)
    return _extract_binding(
        wheel_path,
        CORE_WHEEL_PIN.wheel_member,
        staged_tree_sitter_dir / CP39_TREE_SITTER_BINDING_NAME,
    )


def _load_segments(data: bytes) -> list[tuple[int, int, int]]:
    if len(data) < 64 or data[:4] != b"\x7fELF" or data[4] != 2 or data[5] != 1:
        raise RuntimeError("tree-sitter binding is not a little-endian ELF64 file")
    e_phoff = struct.unpack_from("<Q", data, 32)[0]
    e_phentsize, e_phnum = struct.unpack_from("<HH", data, 54)
    segments: list[tuple[int, int, int]] = []
    for index in range(e_phnum):
        offset = e_phoff + index * e_phentsize
        if offset + 32 > len(data):
            break
        p_type, _flags, p_offset, p_vaddr, _paddr, p_filesz = struct.unpack_from(
            "<IIQQQQ", data, offset
        )
        if p_type == _PT_LOAD:
            segments.append((p_vaddr, p_offset, p_filesz))
    return segments


def _vaddr_to_offset(segments: list[tuple[int, int, int]], vaddr: int) -> int | None:
    for segment_vaddr, segment_offset, segment_size in segments:
        if segment_vaddr <= vaddr < segment_vaddr + segment_size:
            return segment_offset + (vaddr - segment_vaddr)
    return None


def _symbol_table_versions(data: bytes) -> list[int]:
    e_shoff = struct.unpack_from("<Q", data, 40)[0]
    e_shentsize, e_shnum, _e_shstrndx = struct.unpack_from("<HHH", data, 58)
    if e_shnum == 0 or e_shoff == 0:
        return []
    headers: list[tuple[int, ...]] = []
    for index in range(e_shnum):
        offset = e_shoff + index * e_shentsize
        if offset + 64 > len(data):
            return []
        headers.append(struct.unpack_from("<IIQQQQIIQQ", data, offset))
    segments = _load_segments(data)
    versions: list[int] = []
    for header in headers:
        if header[1] != _SHT_SYMTAB:
            continue
        link = header[6]
        if link >= len(headers):
            continue
        string_header = headers[link]
        entry_size = header[9] or 24
        count = header[5] // entry_size
        for index in range(count):
            symbol_offset = header[4] + index * entry_size
            if symbol_offset + 24 > len(data):
                break
            st_name, st_info, _other, _shndx, st_value, st_size = struct.unpack_from(
                "<IBBHQQ", data, symbol_offset
            )
            if (st_info & 0xF) != _STT_OBJECT or st_size < 32 or st_value == 0:
                continue
            name_offset = string_header[4] + st_name
            if name_offset >= len(data):
                continue
            name_end = data.find(b"\x00", name_offset)
            name = data[name_offset:name_end].decode(errors="replace")
            if not name.startswith("language."):
                continue
            file_offset = _vaddr_to_offset(segments, st_value)
            if file_offset is None or file_offset + 4 > len(data):
                continue
            version = struct.unpack_from("<I", data, file_offset)[0]
            if 1 <= version <= 64:
                versions.append(version)
    return versions


def read_grammar_language_abi(path: Path) -> int:
    """Return the tree-sitter language ABI stored in a grammar ``_binding``.

    Grammar wheels keep the ABI as the first field of the ``TSLanguage``
    object. The compiler names that object ``language.<n>`` in the symbol
    table. The product build reads it without executing the Linux binary.
    """
    data = path.read_bytes()
    try:
        versions = _symbol_table_versions(data)
    except RuntimeError as exc:
        raise RuntimeError(f"{path} language ABI is unreadable. {exc}") from exc
    unique = set(versions)
    if len(unique) != 1:
        found = ", ".join(str(version) for version in sorted(unique)) or "none"
        raise RuntimeError(
            f"{path} language ABI is unreadable. Expected one language.* "
            f"symbol version, found {found}."
        )
    return unique.pop()


def overlay_linux_grammar_bindings(vendor_dir: Path, cache_dir: Path) -> tuple[Path, ...]:
    """Replace each staged grammar binding with the Linux wheel member."""
    overlaid: list[Path] = []
    for pin in grammar_wheel_pins():
        package_dir = vendor_dir / pin.package_name
        if not package_dir.is_dir():
            raise RuntimeError(
                f"staged tree-sitter grammar directory not found: {package_dir}"
            )
        wheel_path = download_tree_sitter_wheel(pin, cache_dir)
        destination = package_dir / pin.binding_filename
        _extract_binding(wheel_path, pin.wheel_member, destination)
        _remove_other_bindings(package_dir, pin.binding_filename)
        overlaid.append(destination)
    return tuple(overlaid)


def _remove_excluded_grammar(vendor_dir: Path, package_name: str) -> None:
    package_dir = vendor_dir / package_name
    if package_dir.exists():
        shutil.rmtree(package_dir)
    prefix = f"{package_name}-"
    for entry in list(vendor_dir.iterdir()):
        if (
            entry.is_dir()
            and entry.name.startswith(prefix)
            and entry.name.endswith(".dist-info")
        ):
            shutil.rmtree(entry)


def _exclusion_reason(package_name: str, language_abi: int) -> str:
    detail = _EXPLICIT_ABI_EXCLUSIONS[package_name]
    return (
        f"Excluding {package_name} from the product bundle. "
        f"Language ABI {language_abi} is outside "
        f"{CORE_LANGUAGE_ABI_MIN}-{CORE_LANGUAGE_ABI_MAX} supported by "
        f"{CORE_WHEEL_PIN.distribution} {CORE_WHEEL_PIN.version}. {detail}"
    )


def enforce_grammar_language_abi(vendor_dir: Path) -> tuple[GrammarExclusion, ...]:
    """Drop explicitly excluded grammars the core cannot load.

    Any other grammar outside the core ABI range fails the build. The editor
    still catches an incompatible grammar at runtime when a dev vendor tree
    contains one.
    """
    exclusions: list[GrammarExclusion] = []
    for pin in grammar_wheel_pins():
        binding = vendor_dir / pin.package_name / pin.binding_filename
        if not binding.is_file():
            raise RuntimeError(f"missing grammar binding for ABI check: {binding}")
        language_abi = read_grammar_language_abi(binding)
        if CORE_LANGUAGE_ABI_MIN <= language_abi <= CORE_LANGUAGE_ABI_MAX:
            continue
        if pin.package_name not in _EXPLICIT_ABI_EXCLUSIONS:
            raise RuntimeError(
                f"{pin.package_name} language ABI {language_abi} is outside "
                f"{CORE_LANGUAGE_ABI_MIN}-{CORE_LANGUAGE_ABI_MAX} supported by "
                f"{CORE_WHEEL_PIN.distribution} {CORE_WHEEL_PIN.version}. "
                "Repin the grammar, or add an explicit exclusion with a reason."
            )
        reason = _exclusion_reason(pin.package_name, language_abi)
        _remove_excluded_grammar(vendor_dir, pin.package_name)
        exclusions.append(
            GrammarExclusion(
                package_name=pin.package_name,
                language_abi=language_abi,
                reason=reason,
            )
        )
    return tuple(exclusions)


def stage_linux_grammar_bindings(vendor_dir: Path, cache_dir: Path) -> GrammarStageResult:
    """Overlay Linux grammar bindings, then apply the language ABI rule."""
    overlaid = overlay_linux_grammar_bindings(vendor_dir, cache_dir)
    exclusions = enforce_grammar_language_abi(vendor_dir)
    excluded_names = {item.package_name for item in exclusions}
    kept = tuple(path for path in overlaid if path.parent.name not in excluded_names)
    return GrammarStageResult(overlaid=kept, exclusions=exclusions)
