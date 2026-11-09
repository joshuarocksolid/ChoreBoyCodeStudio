# Pictures

A picture on a button, a label, or a window icon has to travel with the app. Put it in the project's pictures file. A path such as `/home/default/Pictures/logo.png` works on your machine and is blank after you package.

## To add a picture

1. Select the widget. Open the picture, icon, or brush page, and choose the picture row.
2. In a project, click `Add picture…`.
3. Choose a picture file. Code Studio copies it into `forms/resources.qrc`, under a `pictures` folder, and stores a resource path such as `:/pictures/logo.png`.

The first picture creates `forms/resources.qrc` when the project does not have one yet. The form lists that file in its resources. The toast names the file that was made.

The picker shows `THIS FORM'S PICTURES` and `OTHER PICTURES IN THIS PROJECT`. The caption names the pictures file. `Change` picks a different one.

## A form that is not in a project

The button reads `From a file…`. That stores a file path. The picker says the form has nowhere to keep pictures.

## When a path will not survive packaging

The inspector says `Loaded from a file path. A packaged app may not find it.` Click `Add to project pictures`.

The Problems panel uses the same warning. A pictures file that names a missing file is a problem too. See [Form problems](diagnostics.md) for FB031, FB032, and FB503.

Open a `.qrc` file to edit the list. The editor has `Pictures` and `XML`. You can add pictures, rename one, or remove one. If other forms use the picture, the prompt says how many, and a rename updates them when you save.

Pictures larger than 16 MB are refused. Other file types are refused with `Only pictures can go here.`

[Form builder manual](index.md)
