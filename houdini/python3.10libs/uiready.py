# Snippet Library: start the viewer -> Houdini bridge once the UI is up.
try:
    import snippetlib.houdini_io
    snippetlib.houdini_io.start_bridge()
except Exception as exc:
    print("SnippetLibrary: bridge not started (%s)" % exc)
