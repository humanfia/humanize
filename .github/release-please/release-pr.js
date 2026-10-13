// Opens or updates the release pull request for $VERSION against $BRANCH, as
// `release-please release-pr --release-as` does, but with the last release $PREVIOUS where
// it is set. release-please takes the last release to be the one its manifest names, a
// pre-release included, and its command line cannot say otherwise: this is how a release's
// notes cover all that its pre-releases did. release.yml runs it.

const { GitHub, Manifest } = require("release-please");
const { Version } = require("release-please/build/src/version");

(async () => {
  const { GITHUB_REPOSITORY, GH_TOKEN, BRANCH, VERSION, PREVIOUS } = process.env;
  const [owner, repo] = GITHUB_REPOSITORY.split("/");
  const github = await GitHub.create({ owner, repo, token: GH_TOKEN });
  const manifest = await Manifest.fromManifest(github, BRANCH, undefined, undefined, {}, undefined, VERSION);
  if (PREVIOUS) manifest.releasedVersions["."] = Version.parse(PREVIOUS);
  console.log(await manifest.createPullRequests());
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
