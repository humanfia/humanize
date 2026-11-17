// Where Humanize Desktop is downloaded from, and which platform the reader is on.
//
// The installers are assets of the GitHub releases of humanfia/humanize, named with their
// version, so there is no fixed URL to link: the newest release that carries an installer for a
// platform is asked for once, in the browser, and the release page is the link until it answers
// (or if it never does).

export type OS = 'macos' | 'windows' | 'linux'

export const RELEASES = 'https://github.com/humanfia/humanize/releases/latest'

export const PLATFORMS: { key: OS; label: string }[] = [
  { key: 'macos', label: 'macOS' },
  { key: 'windows', label: 'Windows' },
  { key: 'linux', label: 'Linux' },
]

/** The platform this browser runs on, or null where it does not say. */
export function detectOS(): OS | null {
  const nav = navigator as Navigator & { userAgentData?: { platform?: string } }
  const said = `${nav.userAgentData?.platform ?? ''} ${nav.platform ?? ''} ${nav.userAgent ?? ''}`.toLowerCase()
  if (/win/.test(said)) return 'windows'
  if (/mac|iphone|ipad/.test(said)) return 'macos'
  if (/linux|x11|cros|android/.test(said)) return 'linux'
  return null
}

export interface Installer {
  url: string
  version: string
}

const ASSET: Partial<Record<OS, RegExp>> = {
  macos: /-macos-universal\.dmg$/,
  windows: /-windows-x64-setup\.exe$/,
}

interface Release {
  tag_name: string
  draft: boolean
  prerelease: boolean
  assets: { name: string; browser_download_url: string }[]
}

let asked: Promise<Partial<Record<OS, Installer>>> | undefined

/** The newest released installer for each platform that has one. */
export function installers(): Promise<Partial<Record<OS, Installer>>> {
  asked ??= fetch('https://api.github.com/repos/humanfia/humanize/releases?per_page=20')
    .then((r) => (r.ok ? (r.json() as Promise<Release[]>) : []))
    .then((releases) => {
      const found: Partial<Record<OS, Installer>> = {}
      for (const [os, pattern] of Object.entries(ASSET) as [OS, RegExp][]) {
        for (const release of releases) {
          if (release.draft || release.prerelease) continue
          const asset = release.assets.find((a) => pattern.test(a.name))
          if (asset) {
            found[os] = { url: asset.browser_download_url, version: release.tag_name.replace(/^v/, '') }
            break
          }
        }
      }
      return found
    })
    .catch(() => ({}))
  return asked
}
