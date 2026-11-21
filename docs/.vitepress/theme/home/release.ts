// Where Humanize is got from, for the platform the reader is on.
//
// Humanize Desktop's installers are assets of the GitHub releases of humanfia/humanize, named
// with their version, so no address is fixed: the newest release that carries one for a platform
// is asked for once, in the browser. Until it answers, or if it never does, macOS is sent to the
// latest release, where its disk image is, as docs/user/install.md sends it; Windows is offered
// its installer only once a release is found to carry one, and until then the command, which
// there runs in WSL. Linux has no desktop app: it installs the command.

export type OS = 'macos' | 'windows' | 'linux'

export const REPO = 'https://github.com/humanfia/humanize'
export const RELEASES = `${REPO}/releases/latest`
export const INSTALL = 'uv tool install hmz'

/** The platform this browser runs on, or null where it does not say or where Humanize is not
 *  installed: a phone or a tablet. An iPad says it is a Mac, but a Mac has no touch screen. */
export function detectOS(): OS | null {
  const nav = navigator as Navigator & { userAgentData?: { platform?: string } }
  const said = `${nav.userAgentData?.platform ?? ''} ${nav.platform ?? ''} ${nav.userAgent ?? ''}`.toLowerCase()
  if (/iphone|ipad|ipod|android/.test(said)) return null
  if (/win/.test(said)) return 'windows'
  if (/mac/.test(said)) return nav.maxTouchPoints > 1 ? null : 'macos'
  if (/linux|x11|cros/.test(said)) return 'linux'
  return null
}

const ASSET: Record<Exclude<OS, 'linux'>, RegExp> = {
  macos: /-macos-universal\.dmg$/,
  windows: /-windows-x64-setup\.exe$/,
}

interface Release {
  draft: boolean
  prerelease: boolean
  assets: { name: string; browser_download_url: string }[]
}

export type Installers = Partial<Record<Exclude<OS, 'linux'>, string>>

let asked: Promise<Installers> | undefined

/** The newest released installer of each platform that has one. */
export function installers(): Promise<Installers> {
  asked ??= fetch('https://api.github.com/repos/humanfia/humanize/releases?per_page=20')
    .then((answer) => (answer.ok ? (answer.json() as Promise<Release[]>) : []))
    .then((releases) => {
      const found: Installers = {}
      for (const os of Object.keys(ASSET) as (keyof typeof ASSET)[]) {
        for (const release of releases) {
          if (release.draft || release.prerelease) continue
          const asset = release.assets.find((one) => ASSET[os].test(one.name))
          if (asset) {
            found[os] = asset.browser_download_url
            break
          }
        }
      }
      return found
    })
    .catch(() => ({}))
  return asked
}
