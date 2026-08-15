# Minting a Zenodo DOI for `msa-ad`

Everything in this file is a step **you** have to perform, because it needs your
GitHub and Zenodo credentials. The repository side is already prepared:
`CITATION.cff` and `.zenodo.json` are committed, the version is bumped to
`0.1.1`, and the test suite passes.

Read step 0 before touching anything — the order matters, and one step is
irreversible.

---

## Step 0 — Things to know before you start

**Cost.** Nothing here costs money. A Zenodo account is free, and Zenodo mints
DataCite DOIs at no charge. You will not be asked for payment or card details at
any point. If a page asks you to pay, you are not on Zenodo.

**Accounts you will need.**

| What | Required? | Cost |
| --- | --- | --- |
| GitHub account (`Never2land`) | Already have it | — |
| Zenodo account | **Yes — you must create one** | Free |
| ORCID iD | Optional | Free |

You can create the Zenodo account by signing in with GitHub, which also
completes the account link in one move (see step 1).

**You will be asked to authorize an OAuth connection** between Zenodo and
GitHub. Zenodo requests `admin:repo_hook`, `read:org` and `user:email` — it
needs `admin:repo_hook` to install the webhook that notifies it when you publish
a release. This is expected and is how the integration works. Grant it only on
the real `zenodo.org` domain.

**This step is irreversible.** Once Zenodo publishes a record and mints a DOI,
you cannot delete it yourself — DOIs are meant to be permanent. You can edit
most metadata afterwards, and you can publish a corrected new version, but you
cannot un-publish. If you want a dry run first, do the whole flow against
<https://sandbox.zenodo.org> (a separate account, separate throwaway DOIs) and
then repeat it on the real site.

**Ordering constraint — the most common way to get this wrong.** Zenodo only
archives releases published **after** you enable the repository. Enabling it
afterwards will not retroactively pick up an existing release. So: enable first
(steps 1–2), release second (step 4).

**Second ordering constraint.** Zenodo reads `.zenodo.json` out of the source
archive of the tag you release. The existing `v0.1.0` tag was cut before those
files existed, so releasing `v0.1.0` would produce a record with no metadata.
That is why the version is now `0.1.1` — release the new tag, not the old one.

---

## Step 1 — Create/sign in to Zenodo and link GitHub

1. Go to <https://zenodo.org>.
2. Click **Sign up** (or **Log in** if you already have an account).
3. Choose **Sign up with GitHub**. This creates the Zenodo account and links
   GitHub in a single step.
   - If you instead sign up with an email and password, link GitHub afterwards:
     click your profile menu in the header → **Linked accounts** → **Connect**
     next to GitHub.
4. Authorize the application on the GitHub screen that appears.
5. Confirm it worked: on the **Linked accounts** page there should be a green
   tick next to GitHub.

---

## Step 2 — Enable the `msa-ad` repository

1. Make sure <https://github.com/Never2land/msa-ad> is **public**. Private
   repositories do not appear in Zenodo's list.
2. Go to <https://zenodo.org/account/settings/github/> (also reachable from the
   profile menu → **GitHub**).
3. Click **Sync now** in the header. This re-reads your repository list from
   GitHub.
4. Find `Never2land/msa-ad` in the list and **toggle the slider to On**.
5. Refresh the page. The repository should now appear under the enabled
   repositories, showing "No releases yet."

If `msa-ad` does not appear after syncing: check the repo is public, check you
are the owner or have admin rights on it, and wait a few seconds before syncing
again.

---

## Step 3 — Push the prepared commits

Run these locally. Nothing has been pushed for you.

```bash
cd /Users/linlinwang/Code/msa-ad

# Review what is about to go out
git log --oneline origin/main..HEAD
git show --stat HEAD

# Push the commits
git push origin main
```

---

## Step 4 — Cut the release that triggers the DOI

Do this **only after step 2 shows the repository enabled.**

### Option A — GitHub CLI (you are already authenticated as `Never2land`)

```bash
cd /Users/linlinwang/Code/msa-ad

git tag -a v0.1.1 -m "v0.1.1 — add citation metadata for archival"
git push origin v0.1.1

gh release create v0.1.1 \
  --repo Never2land/msa-ad \
  --title "v0.1.1" \
  --notes "Adds CITATION.cff and .zenodo.json so the repository can be archived and cited. No changes to the analysis code; the test suite is unchanged and passing."
```

### Option B — GitHub web UI

1. Push the tag first (`git tag -a v0.1.1 -m "..."` then
   `git push origin v0.1.1`), or let the UI create it for you.
2. Go to <https://github.com/Never2land/msa-ad/releases/new>.
3. **Choose a tag:** `v0.1.1`. **Target:** `main`.
4. **Release title:** `v0.1.1`. Fill in the description.
5. Click **Publish release** — *not* **Save draft**. Draft releases do not fire
   the webhook and Zenodo will never see them.

Within a minute or so of publishing, Zenodo receives the webhook, downloads the
source archive of the tag, reads `.zenodo.json`, and creates a published record
with a freshly minted DOI. There is nothing to approve — it is automatic.

---

## Step 5 — Find your DOIs

1. Go back to <https://zenodo.org/account/settings/github/>.
2. `Never2land/msa-ad` now shows a DOI badge. Click through to the record.
3. On the record page, look at the right-hand sidebar for the **Versions** box.
   It lists `v0.1.1` with its own DOI, and beneath the list a line reading
   roughly:

   > *Cite all versions? You can cite all versions by using the DOI
   > `10.5281/zenodo.NNNNNNN`. This DOI represents all versions, and will always
   > resolve to the latest one.*

   That second number is your **concept DOI**.

### Version DOI vs concept DOI — which to cite

Zenodo mints **two** DOIs, and they are not interchangeable.

| | Concept DOI | Version DOI |
| --- | --- | --- |
| Also called | "all versions" DOI | "this version" DOI |
| Points at | The project as an evolving whole | One frozen snapshot (`v0.1.1`) |
| Resolves to | Always the **latest** version | Always that **exact** version, forever |
| Changes when you release again? | No — same number forever | No — a new one is minted per release |

They are numerically adjacent (typically the concept DOI is one lower), which
makes them easy to confuse. Check the sidebar wording rather than guessing.

**Cite the concept DOI** in the README, on a CV, in a project description, or
anywhere you mean "this software" as an ongoing thing. Readers following it land
on whatever is current.

**Cite the version DOI** when reproducibility is the point — a paper reporting
results computed with a specific build, where someone must be able to retrieve
byte-identical code. The concept DOI is wrong there, because it will drift to a
newer version than the one you actually ran.

For this repository's own README, the concept DOI is the right choice.

---

## Step 6 — Wire the DOI back into the repository

Three placeholders are waiting for the number. Once you have the concept DOI:

1. **`README.md`** — replace `10.5281/zenodo.XXXXXXX` in the Citation section
   with the concept DOI, and delete the `*(pending — see ZENODO-STEPS.md)*`
   note and the surrounding HTML comment.

2. **`README.md`** (optional) — add the badge just under the title. Zenodo gives
   you the exact markdown under **Cite as** → the badge dropdown on the record
   page. It looks like:

   ```markdown
   [![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.NNNNNNN.svg)](https://doi.org/10.5281/zenodo.NNNNNNN)
   ```

   Use the **concept** DOI so the badge tracks the latest release.

3. **`CITATION.cff`** — uncomment the `identifiers:` block at the bottom of the
   file and paste the concept DOI in.

Then commit and push:

```bash
cd /Users/linlinwang/Code/msa-ad
git add README.md CITATION.cff
git commit -m "Record the Zenodo concept DOI in the README and citation metadata"
git push origin main
```

You do **not** need to cut a new release for this. The DOI already exists; you
are only documenting it. It will be folded into whatever you release next.

---

## Optional — fill in the author placeholders

`CITATION.cff` has commented-out `orcid:` and `affiliation:` fields under your
name. Both were deliberately left blank rather than guessed at.

- **ORCID iD.** Free, and worth having if you publish: register at
  <https://orcid.org/register>. Then uncomment the `orcid:` line in
  `CITATION.cff` and add the matching entry to `.zenodo.json` (JSON has no
  comments, so there is no placeholder there — add it by hand):

  ```json
  "creators": [
    { "name": "Wang, Linlin", "orcid": "0000-0000-0000-0000" }
  ]
  ```

  Note the differing formats: `CITATION.cff` wants the full
  `https://orcid.org/...` URL, `.zenodo.json` wants the bare digits.

- **Affiliation.** Add only if you want it publicly attached to the deposit.

Metadata changes only reach Zenodo on the *next* release. To correct an existing
record sooner, use **Edit** on the Zenodo record page — metadata is editable
after publication even though the record itself cannot be deleted.

---

## Which file does what

Both metadata files are committed, and they serve different consumers:

- **`.zenodo.json`** — read by Zenodo. When both files are present, Zenodo uses
  **only** `.zenodo.json` and ignores `CITATION.cff` entirely.
- **`CITATION.cff`** — read by GitHub, which renders the "Cite this repository"
  button in the repo sidebar. Also read by reference managers and by `cffconvert`.

So both are needed, and they must be kept in sync by hand. If you change the
title, description, keywords or version, change it in both.

---

## Releasing again later

The setup is one-time. For every subsequent release:

1. Bump the version in **four** places: `pyproject.toml`, `msa_ad/__init__.py`,
   `CITATION.cff` (`version:` and `date-released:`), and `.zenodo.json`
   (`version`).
2. Commit, tag, push the tag, publish the GitHub release.
3. Zenodo mints a new version DOI automatically and the concept DOI starts
   resolving to it.
