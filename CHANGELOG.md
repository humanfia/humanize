# Changelog

## 0.1.0-beta.2 (2026-10-09)


### ⚠ BREAKING CHANGES

* publishing a GitHub release no longer publishes to PyPI; run release.yml and merge the release pull request it opens.

### Fixes

* **agents:** let fenced Codex initialize TLS on macOS and fail turns that end in error ([#281](https://github.com/humanfia/humanize/issues/281)) ([6a86daa](https://github.com/humanfia/humanize/commit/6a86daa558bfd013dc63cabe2ca87710b10b0caf))
* **agents:** let fenced Codex initialize TLS on macOS and fail turns that end in error ([#282](https://github.com/humanfia/humanize/issues/282)) ([6a86daa](https://github.com/humanfia/humanize/commit/6a86daa558bfd013dc63cabe2ca87710b10b0caf))
* **coganchor:** let a fence write /proc, and let local and user of ALL write what they say ([#278](https://github.com/humanfia/humanize/issues/278)) ([bb9446a](https://github.com/humanfia/humanize/commit/bb9446a7ab9b8bf5f4827f1909787552cf3327cc)), refs [#276](https://github.com/humanfia/humanize/issues/276)
* **tui:** offer a backend's missing extra as hmz[&lt;extra&gt;] when humanize came from PyPI ([#273](https://github.com/humanfia/humanize/issues/273)) ([0c564d7](https://github.com/humanfia/humanize/commit/0c564d7fafc86d23a6504fb54c4fa77bb00ad079))


### CI

* release only from release/X.Y branches, through a release pull request release.yml opens ([#275](https://github.com/humanfia/humanize/issues/275)) ([1e021bd](https://github.com/humanfia/humanize/commit/1e021bd15cbaf5bc2025332374e539f93d004ee2))
