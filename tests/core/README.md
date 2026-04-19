# Core Tests

Core tests cover pure project logic.
They avoid subprocesses, PTYs, network access, and filesystem writes outside `tmp_path`.
See `../CONVENTIONS.md` before adding or moving tests here.
