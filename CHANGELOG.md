# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.23.0] - 2026-04-05

### Added

- Living Wiki: `source_files` and `source_commit` frontmatter fields for tracking which source code files a wiki page documents
- Stale page detection in `synapse wiki status` and `synapse wiki lint` — identifies pages whose tracked source files have changed
- `synapse wiki refresh [--apply]` command — lists stale pages and optionally updates `source_commit` to current HEAD
- `synapse wiki init` command — creates skeleton `synthesis-architecture.md` and `synthesis-patterns.md` pages with idempotent index entries
- `learning` page type for recording bug fixes and discovered patterns
- `GET /api/wiki/graph` Canvas endpoint — returns a Mermaid diagram of wiki page `[[wikilink]]` relationships

### Documentation

- Updated synapse-reference.md, README.md, llm-wiki.md with new wiki commands and features
- Updated site-docs CLI and API reference pages
- Added `source_files` and `source_commit` to wiki-schema.md frontmatter specification


## [0.22.0] - 2026-04-05

### Added

- `synapse worktree prune` CLI command — detects and removes orphan worktrees whose directories no longer exist
- `synapse worktree` subcommand group for worktree management

### Fixed

- Canvas Database view no longer lists `.db` files from `.synapse/worktrees/` directories


[0.23.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.22.0...v0.23.0
[0.22.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.21.0...v0.22.0
[0.21.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.20.0...v0.21.0
[0.20.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.19.5...v0.20.0
[0.19.5]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.19.4...v0.19.5
[0.19.4]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.19.3...v0.19.4
[0.19.3]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.19.2...v0.19.3
[0.19.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.19.1...v0.19.2
[0.19.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.19.0...v0.19.1
[0.19.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.18.4...v0.19.0
[0.18.4]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.18.3...v0.18.4
[0.18.3]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.18.2...v0.18.3
[0.18.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.18.1...v0.18.2
[0.18.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.18.0...v0.18.1
[0.18.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.16...v0.18.0
[0.17.16]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.15...v0.17.16
[0.17.15]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.14...v0.17.15
[0.17.14]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.13...v0.17.14
[0.17.13]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.12...v0.17.13
[0.17.12]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.11...v0.17.12
[0.17.11]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.10...v0.17.11
[0.17.10]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.9...v0.17.10
[0.17.9]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.8...v0.17.9
[0.17.8]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.7...v0.17.8
[0.17.7]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.6...v0.17.7
[0.17.6]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.5...v0.17.6
[0.17.5]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.4...v0.17.5
[0.17.4]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.3...v0.17.4
[0.17.3]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.2...v0.17.3
[0.17.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.1...v0.17.2
[0.17.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.17.0...v0.17.1
[0.17.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.16.2...v0.17.0
[0.16.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.16.1...v0.16.2
[0.16.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.16.0...v0.16.1
[0.16.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.15.11...v0.16.0
[0.15.11]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.15.10...v0.15.11
[0.15.10]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.15.9...v0.15.10
[0.15.9]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.15.8...v0.15.9
[0.15.8]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.15.7...v0.15.8
[0.15.7]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.15.6...v0.15.7
[0.15.6]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.15.5...v0.15.6
[0.15.5]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.15.4...v0.15.5
[0.15.4]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.15.3...v0.15.4
[0.15.3]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.15.2...v0.15.3
[0.15.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.15.1...v0.15.2
[0.15.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.15.0...v0.15.1
[0.15.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.14.0...v0.15.0
[0.14.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.13.0...v0.14.0
[0.13.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.12.2...v0.13.0
[0.12.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.12.1...v0.12.2
[0.12.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.12.0...v0.12.1
[0.12.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.21...v0.12.0
[0.11.21]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.20...v0.11.21
[0.11.20]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.19...v0.11.20
[0.11.19]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.18...v0.11.19
[0.11.18]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.17...v0.11.18
[0.11.17]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.16...v0.11.17
[0.11.16]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.15...v0.11.16
[0.11.15]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.14...v0.11.15
[0.11.14]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.13...v0.11.14
[0.11.13]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.12...v0.11.13
[0.11.12]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.11...v0.11.12
[0.11.11]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.10...v0.11.11
[0.11.10]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.9...v0.11.10
[0.11.9]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.8...v0.11.9
[0.11.8]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.7...v0.11.8
[0.11.7]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.6...v0.11.7
[0.11.6]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.5...v0.11.6
[0.11.5]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.4...v0.11.5
[0.11.4]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.3...v0.11.4
[0.11.3]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.2...v0.11.3
[0.11.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.1...v0.11.2
[0.11.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.11.0...v0.11.1
[0.11.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.10.1...v0.11.0
[0.10.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.10.0...v0.10.1
[0.10.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.9.5...v0.10.0
[0.9.5]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.9.4...v0.9.5
[0.9.4]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.9.3...v0.9.4
[0.9.3]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.9.2...v0.9.3
[0.9.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.9.1...v0.9.2
[0.9.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.8.6...v0.9.0
[0.8.6]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.8.5...v0.8.6
[0.8.5]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.8.4...v0.8.5
[0.8.4]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.8.3...v0.8.4
[0.8.3]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.8.2...v0.8.3
[0.8.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.8.1...v0.8.2
[0.8.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.12...v0.7.0
[0.6.12]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.11...v0.6.12
[0.6.11]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.10...v0.6.11
[0.6.10]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.9...v0.6.10
[0.6.9]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.8...v0.6.9
[0.6.8]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.7...v0.6.8
[0.6.7]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.6...v0.6.7
[0.6.6]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.5...v0.6.6
[0.6.5]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.4...v0.6.5
[0.6.4]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.3...v0.6.4
[0.6.3]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.2...v0.6.3
[0.6.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.1...v0.6.2
[0.6.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.5.2...v0.6.0
[0.5.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.4.4...v0.5.0
[0.4.4]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.4.3...v0.4.4
[0.4.3]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.4.2...v0.4.3
[0.4.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.25...v0.4.0
[0.3.25]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.24...v0.3.25
[0.3.24]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.23...v0.3.24
[0.3.23]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.22...v0.3.23
[0.3.22]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.21...v0.3.22
[0.3.21]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.20...v0.3.21
[0.3.20]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.19...v0.3.20
[0.3.19]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.18...v0.3.19
[0.3.18]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.17...v0.3.18
[0.3.17]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.16...v0.3.17
[0.3.16]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.15...v0.3.16
[0.3.15]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.14...v0.3.15
[0.3.14]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.13...v0.3.14
[0.3.13]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.12...v0.3.13
[0.3.12]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.11...v0.3.12
[0.3.11]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.10...v0.3.11
[0.3.10]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.9...v0.3.10
[0.3.9]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.8...v0.3.9
[0.3.8]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.7...v0.3.8
[0.3.7]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.6...v0.3.7
[0.3.6]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.5...v0.3.6
[0.3.5]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.4...v0.3.5
[0.3.4]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.3...v0.3.4
[0.3.3]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.30...v0.3.0
[0.2.30]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.29...v0.2.30
[0.2.29]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.28...v0.2.29
[0.2.28]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.27...v0.2.28
[0.2.27]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.26...v0.2.27
[0.2.26]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.25...v0.2.26
[0.2.25]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.24...v0.2.25
[0.2.24]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.23...v0.2.24
[0.2.23]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.22...v0.2.23
[0.2.22]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.21...v0.2.22
[0.2.21]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.20...v0.2.21
[0.2.20]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.19...v0.2.20
[0.2.19]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.18...v0.2.19
[0.2.18]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.17...v0.2.18
[0.2.17]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.16...v0.2.17
[0.2.16]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.15...v0.2.16
[0.2.15]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.14...v0.2.15
[0.2.14]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.13...v0.2.14
[0.2.13]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.12...v0.2.13
[0.2.12]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.11...v0.2.12
[0.2.11]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.10...v0.2.11
[0.2.10]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.9...v0.2.10
[0.2.9]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.8...v0.2.9
[0.2.8]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.7...v0.2.8
[0.2.6]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.5...v0.2.6
[0.2.5]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/s-hiraoku/synapse-a2a/releases/tag/v0.1.0
