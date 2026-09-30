# App logos (optional)

Put your own logo files here and the viewer shows them instead of the
text badges. Nothing in this folder except this README is tracked by git,
because the Houdini and Nuke marks are trademarks of SideFX / Foundry.

    viewer/static/logos/houdini.svg   (or .png / .webp / .jpg)
    viewer/static/logos/nuke.svg

Recommended: transparent background, roughly 3:1 or squarer; they are
shown 22 px high in the list and 26 px in the detail header.
If this folder has no file for an app, the viewer looks for the logo shipped
with an installed copy of that app (Houdini: icons.zip MISC/logo.svg,
Nuke: plugins/icons/NukeApp128.png) and caches it under
%LOCALAPPDATA%\SnippetLibrary\logos. No install found -> text badge.
Restart the viewer after adding a file.
