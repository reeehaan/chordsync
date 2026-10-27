# Accounts, profiles and the shared song library: plan

Status: **Phase 1 server side is live** (2026-10-27); the app sign-in screens are not built yet. It replaces the shared demo tokens
(`docs/cloud/s7-t06-demo-auth.md`) and the "every tester sees every song" library.

## Decisions taken

1. **No paid Apple Developer membership** for now. See "What this rules out" below.
2. **Analyses are private.** Users never see each other's analyses or audio. The only thing
   shared is a **catalogue timeline** (chords, beats, timings) per recording.
3. One account per phone is a goal, but it cannot be enforced strongly without Apple's
   device checks; the plan limits what a second account can gain instead.

## What this rules out (free Apple account)

- **No distribution to other iPhone users at all.** A free account can install the app only
  on the developer's own devices (a few), and the build expires every 7 days. No TestFlight,
  no App Store. Real users on iPhone need the paid membership.
- No Sign in with Apple, DeviceCheck, App Attest or push notifications.
- **iOS only, by decision (2026-10-27).** No Android build. Until the paid membership exists,
  ChordSync runs on the developer's own iPhone, so accounts and the shared catalogue are built
  and tested there (extra test accounts can be made from the simulator). Opening the app to
  other iPhone users waits for the paid membership.

## Concepts (kept separate on purpose)

| Concept | Meaning | Visible to |
|---|---|---|
| **User** | An account with a profile and taste | Only the user |
| **Recording** | One specific recording (audio fingerprint), such as a studio version of a song | Catalogue (no owner shown) |
| **Catalogue timeline** | The best chord, beat and lyric timeline known for a recording | Everyone, without the audio |
| **Analysis** | A user's own run on their own file | Only the owner |
| **Library** | A user's list of analyses and saved recordings | Only the owner |

Audio files stay in the owner's private storage and are never served to anyone else.
Only derived data (the catalogue timeline) is shared. Showing lyrics to everyone is a
licensing question to settle before launch (this is not legal advice).

## Sign-in and one account per phone

- **Amazon Cognito** user pool. Start with email and a one-time code, which needs no paid membership.
  Add Sign in with Apple when the membership exists. If Google sign-in is ever offered in the
  App Store build, Apple then requires Sign in with Apple too.
- The API Gateway checks the Cognito token itself (JWT authorizer), so requests without a
  valid token never reach the Lambda. Owner id = the token's subject, never a request field.
- **One account per phone, honestly:**
  - Store a random install id in the iOS Keychain and send it at
    sign-up. The server allows a few accounts per install id. A wiped phone or a new install
    can bypass it; this is a speed bump, not a wall.
  - Verified email, a per-address and per-network sign-up rate limit, and a free quota per
    account.
  - **The real defence is cost:** a second account gains little because analysis is
    de-duplicated (below) and each account has a daily quota.
  - With the paid membership later: DeviceCheck (two bits per device that survive
    reinstalls) and App Attest. Avoid hardware ids and advertising ids.
- **Account deletion in the app** is required by Apple (guideline 5.1.1(v)) and good practice
  elsewhere: delete the profile, the library, the private audio and the personal data;
  keep only anonymous catalogue data.

## Profile and taste

- Onboarding, skippable, three short steps: display name; skill level and instrument
  (acoustic or electric); taste (genre chips, a few favourite artists).
- Do not collect a birth date or exact location unless a feature needs it. If you ever
  collect age, children's-privacy rules apply. Sri Lanka's Personal Data Protection Act
  applies to the profile data: record purpose, allow export and deletion.
- Taste is stored as plain preferences, with genres from an open source such as MusicBrainz
  tags (not Spotify data, whose terms restrict this use).

## Songs already in the cloud: how to reuse an analysis

Same song, different timeline, because files differ (encodes, leading silence, versions).
Match in steps, cheapest first. The phone computes the hash and fingerprint, so a match costs
no upload:

1. **Same file** (SHA-256 of the file): reuse the analysis at once. Zero compute.
2. **Same recording** (audio fingerprint such as Chromaprint, plus a length check): offer
   "use the existing timeline" or "analyse my file". Reuse needs only a small **time offset**
   so the timeline lines up with this user's file; the fingerprint comparison gives it.
3. **Different version** (live, remaster, cover): a separate recording. The user may choose.

Which timeline is the catalogue's best for a recording: the first analysis starts it; a later
analysis replaces it only if its quality score is higher (confidence, agreement of
the checks). Never show who made it. Provide a "report wrong chords" action.

## Library, quotas and scale

- DynamoDB tables: `Users`, `Devices` (install ids), `Profile`, `Recordings`
  (fingerprint, length), `CatalogueTimelines`, `Analyses`, `Library` (user to analysis),
  `PracticeEvents`. S3: private per-user audio prefix; catalogue timelines by recording id.
- Per-user daily analysis quota and a **fair queue** so one account cannot hold the single
  worker. A DynamoDB expiry on unfinished uploads, and a per-user cap on open uploads, stop
  unbounded growth. A real index (user id, created time) replaces the table scan.
- Suggestions start as a scoring Lambda: taste match, skill level, and "songs made of chords
  you already know". Learn from practice events later; avoid managed recommenders until
  there is real usage.

## Security carry-overs from the 2026-10-26 audit

The account design closes these by construction: shared throttle and anonymous traffic (the
gateway rejects untokened requests); revoked tokens (Cognito sessions and refresh tokens can
be revoked); library table scan and queue fairness (index, quotas, fair queue); the shared
library serving other people's audio (private audio). Still to do separately: pip hash
pinning, the container exception re-review before 2026-11-09, and a new image deploy for the
code fixes already committed.

## Phases and tasks

| Phase | Work | Needs money |
|---|---|---|
| 1 | Cognito, gateway token check, owner id from the token, private library, migrate demo testers by hand | No |
| 2 | Onboarding and profile (taste, skill), export and account deletion | No |
| 3 | File hash reuse (exact duplicates) | No |
| 4 | Fingerprint match, offset alignment, catalogue timeline with quality score | No |
| 5 | Quotas, fair queue, index, TTLs | No |
| 6 | Suggestions (rules), then practice-based learning | No |
| 7 | Sign in with Apple, DeviceCheck, App Attest | Paid Apple membership |

## Open questions

- When (if ever) to buy the paid Apple membership, which is the gate to other iPhone users.
- Are lyrics shown to everyone, or only to users who hold the audio file?
- Should a user be able to keep their own analysis next to the catalogue one when they differ?
- Sign-in at launch: email code only (the plan's default), or also Google?

## Phase 1 progress (2026-10-27)

Live in AWS, applied with the owner's approval and MFA:

| Item | Value |
| --- | --- |
| User pool | `ap-southeast-1_kmpQnHrL8` (`chordsync-demo-users`), Essentials tier, email one-time code, deletion protection on |
| App client | `53ko8n7agjn615b1j2396iogvu`, no secret, access token 60 minutes, refresh token 30 days, sign-out revokes it |
| Sender | `ChordSync <chordsync.app@gmail.com>`, verified in SES (the account is in the SES sandbox: 200 emails a day, verified recipients only) |
| API image | `api-3fb8d07`, `sha256:0926ae79fdfe4b231fc05522fd133ee6c9bd4936e76618ac841efe7eccae60be` |
| New routes | `GET /analysis/mine`, `GET /analysis/mine/{job_id}/audio` |

Findings from building it:

- AWS refuses a pool that does not list PASSWORD as an allowed first factor, so the pool
  allows `PASSWORD` and `EMAIL_OTP`. Accounts are created without a password and the app
  only uses the email code.
- Email codes need SES, not Cognito's built-in sender. While in the sandbox, every address
  that should receive a code must be verified in SES first.
- Cognito access tokens are checked inside the API (`backend/api/app/cognito_auth.py`),
  standard library only. A signed-out token stays valid until it expires (at most an hour).
- The shared library (`/analysis/library`) now lists only catalogue songs, which are jobs
  with no owner or a demo-token owner. A signed-in user's analyses are private and appear
  only under `/analysis/mine`. Old songs belong to nobody's own list.
- The demo token still works. It is switched off at the end of Phase 1.

Still to do in Phase 1: the app's sign-in screens, secure token storage and sign-out; a real
sign-in test; then switching the demo token off.
