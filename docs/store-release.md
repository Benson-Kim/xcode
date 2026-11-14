# App Store and Play Store release

App id `ke.co.priori.xcode` on both stores (fixed for good after the first release). Each build has one server built
in, set by its profile in `apps/mobile/eas.json`:

- `staging`, for testers and screenshots: `https://xcode-stg-api.priori.co.ke`, with invitation links verified against
  `https://xcode.stg.priori.co.ke`. Play's Internal testing track and TestFlight testers get these builds.
- `production`, only for the build sent for review, which is the build the public downloads:
  `https://api.xcode.mgr.priori.co.ke`, the live instance with real customers, and `https://xcode.mgr.priori.co.ke`.
  Testing never runs against it. The only store account on it is the review login, in its own Demo Fleet
  organization.

## Already in place

- Apple Developer and Google Play Console accounts. EAS is signed in as an owner of `priori-technlogies-limited`.
- Android target API 36 (Expo SDK 57, React Native 0.86), which meets Play's target level for new apps.
- Privacy policy: https://xcode.mgr.priori.co.ke/privacy
- Account deletion: in the app (More, Delete my account) and on the web at https://xcode.mgr.priori.co.ke/account-deletion
- Export compliance: `usesNonExemptEncryption: false`, so App Store Connect does not ask per build.
- Only the `INTERNET` permission on Android and no purpose strings on iOS (no camera, photos, location, Face ID).
- No self-updater in store builds (`app.config.ts` refuses `EXPO_PUBLIC_UPDATE_URL`).
- Version numbers come from EAS (`appVersionSource: remote`, `autoIncrement`).
- Play icon and feature graphic: `apps/mobile/store/`.

## What can start before any build

- Play Console: create the app and fill in App content, Store settings and the store listing (section 2, steps 1 and
  5). No build is needed; the first upload fixes the package name.
- App Store Connect: the record needs the bundle id registered first. Let the first iOS build register it (section 3):
  EAS then turns on Associated Domains, which the invitation links need. A bundle id registered by hand needs that
  capability ticked.
- The review login (section 1, step 3), once the `master` deploy is live.
- Availability: Kenya only on both stores. The app accepts only Kenyan phone numbers, and the stores' EU trader
  declaration then does not apply.

## 1. Server, before any submission

The reviewers sign in to the live instance, so it must run the release these builds expect and hold the review login.

1. Merge PR #15 (`feat/review-organization`) into `develop`, then `develop` into `master`. CI deploys `master` to the
   migration instance.
2. Once, on the droplet: `xcode-migration-instance/droplet/9-auto-update.sh`. Check that
   https://api.xcode.mgr.priori.co.ke/release answers with the `master` commit.
3. `review-account create` on the droplet, as root, once `/release` answers the `master` commit. Choose the email and
   a Kenyan mobile number (07..., 01... or +254...) that no real account uses; no text message is sent to it.

   ```bash
   bash -c 'set -a; for f in api database mail admin; do . /etc/xcode-mgr/$f.env; done; set +a; /opt/xcode-mgr/current/venv/bin/xcode-api review-account create --email EMAIL --phone PHONE'
   ```

   The first run makes the Demo Fleet (up to 2 minutes). It prints a PIN and a six-digit code once: the code answers the
   new-device step after the PIN. Keep both in a password manager, not in this repository. Run it again only for a new
   submission (each run replaces both).

4. Sign in with that login on a freshly installed production build, on a phone that has never used it, before you give
   it to a reviewer.
5. Build `staging` from a clean checkout of `develop` (which CI deploys to stg) and `production` from a clean checkout
   of `master` (which CI deploys to the live instance). EAS uploads uncommitted files too, so a build from a tree with
   work in progress ships that work.
6. Screenshots and testing use stg. For screenshots with sample data, not anyone's real records, make a review login
   on stg too, on the droplet as root (the same steps as step 3, with stg's files):

   ```bash
   bash -c 'set -a; for f in api database mail admin; do . /etc/xcode-stg/$f.env; done; set +a; /opt/xcode-stg/current/venv/bin/xcode-api review-account create --email EMAIL --phone PHONE'
   ```

## 2. Android (Google Play)

1. Play Console, Create app: name (see Listing), default language English (United States), App, Free, and accept the
   two declarations. Then Store settings: category Business, the contact email and website.
2. Build from a fresh clone (section 1, step 5), never from this working folder. For testers, `develop` and the
   `staging` profile:

   ```bash
   git clone --branch develop --single-branch --depth 1 https://github.com/Benson-Kim/xcode.git xcode-build
   cd xcode-build && npm ci
   cd apps/mobile && eas build --platform android --profile staging --non-interactive --no-wait
   ```

   For review, the same with `--branch master` and `--profile production`. EAS keeps the upload keystore and one
   version code for both profiles (one higher each build), so no prompt comes up. The build page link it prints shows
   progress (about 15 to 30 minutes) and the `.aab` download when it is done.

3. Upload by hand: staging builds to Testing, Internal testing; production builds to Production (Create new release,
   save it as a draft until the listing is complete, then send it for review). Leave "Include app versions from your
   previous release" off.
4. App integrity, App signing: copy both SHA-256 fingerprints (app signing key and upload key). Both profiles share
   them, so set the same `ANDROID_CERT_SHA256=<signing>,<upload>` on both cPanel web apps (`xcode-mgr-web`, and the
   one for `xcode.stg.priori.co.ke`) and restart each. Check that `/.well-known/assetlinks.json` answers 200 on both.
5. Fill App content, Store settings and the store listing (Play Console, page by page, below). Add testers by email.
   Choose Kenya as the country of each track you release on.
6. A phone gets the highest version code among the tracks its account can see. Once a production release rolls out,
   internal testers move to it (and to the live instance) unless Internal testing holds a newer staging build, so
   build staging again after each production build.
7. Later builds can go up with `eas submit --platform android --profile staging` (a draft on Internal testing) or
   `--profile production` (a draft on Production). It needs a Google service account key, added once with
   `eas credentials` (Android, Google Service Account) so it stays on EAS and never in this repository.
8. An organization developer account can release to Production without a closed test; a personal one must first run
   a closed test with 12 testers for 14 days.

## Play Console, page by page

The app is the draft "xcode" (`ke.co.priori.xcode`) under Priori's developer account. Its Dashboard, Set up your app,
ticks each task once it is saved. Until Google reviews the app, internal testers see the temporary name
"ke.co.priori.xcode (unreviewed)". The "Declare your trader status" banner is for the EU only; the app goes to Kenya
only, so it can wait.

**App content** (Policy and programs). Done on 2026-11-13, except where marked.

- Privacy policy: https://xcode.mgr.priori.co.ke/privacy
- Sign in details (App access): All or some functionality is restricted. One instruction set, "Demo Fleet review
  login": the review phone as the user name, the PIN as the password, and the App access text below with the code in
  Any other information. Leave "Allow Android to use the credentials" unticked. Updated on 2026-11-13 with the
  review login's own phone, PIN and code, after that login was tried on the web. A new `review-account create` run
  replaces the PIN and code, so update them here (and in App Store Connect) after every run.
- Ads: no ads.
- Content rating: no to every content question (Other declarations).
- Target audience: 18 and over; nothing in the listing appeals to children.
- Data safety: the Privacy answers below; deletion URL https://xcode.mgr.priori.co.ke/account-deletion
- Government apps: no.
- Financial features: "My app doesn't provide any financial features". Nobody pays, borrows, saves or invests
  through the app; "Other" would only add a documentation step for a service it does not offer.
- Health: no health features.
- Advertising ID, asked after the first upload: no. The app has no ad or analytics library.

**Store settings** (Grow users, Store presence). Done on 2026-11-13.

- App category: App, Business, no tags.
- Store listing contact details: email ma3hub@gmail.com, website https://priori.co.ke, no phone. Shown publicly;
  Save and publish applies it at once.

**Main store listing** (Grow users, Store presence, Store listings, Default store listing; English (United States)).

- App details, done on 2026-11-13 (saved as draft): name `XCODE Fleet`, short description and full description from
  Listing below, with each list item starting "• ".
- Graphics, done on 2026-11-13: Add assets, Upload, then pick the file (it opens your file picker, so you do this
  one). App icon `apps/mobile/store/play-icon-512.png`, feature graphic
  `apps/mobile/store/play-feature-graphic-1024x500.png`. Then Save as draft.
- Phone screenshots, to do: 2 to 8 (Screenshots below), taken on a phone with the staging build from Internal
  testing, signed in with the stg review login (section 1, step 6). Tablet, desktop and XR screenshots are optional;
  leave them out.

**Test and release, Internal testing.** Section 2, steps 2 to 5.

- Release 3 (1.0.0), rolled out on 2026-11-13, is a production build (from `master` 550465c, so it talks to the live
  instance), made before testing moved to stg:
  https://expo.dev/accounts/priori-technlogies-limited/projects/xcode/builds/866b8f85-194b-40ca-80f4-7eef8a01b330
  To do: replace it with the first staging build before anyone tests or takes screenshots. That build is versionCode
  4, finished on 2026-11-13 from `b6ac639` (`chore/mobile-staging-profile`, PR #16); the `.aab` is on its page:
  https://expo.dev/accounts/priori-technlogies-limited/projects/xcode/builds/3e9d0d3e-4e2b-4c9d-807f-c9a6f9ca9733
  Versions 2 (from a0e4a12, released on 2026-11-11) and 3 must not be added back to Internal testing.
- Upload: Play App Signing was already on, so it asks nothing. Play's warning that the bundle has no deobfuscation
  file is expected: the build does not turn on R8, so there is no mapping file to upload.
- Testers, done: the email list "Ma3hub" is ticked on the Testers tab (11 people since 2026-11-13, when the developer's
  own Google account was added). Email lists belong to the developer account and are shared by all its apps. Each
  phone opens the join link https://play.google.com/apps/internaltest/4700636582492010860, accepts, then installs
  from Play.
- App signing, read on 2026-11-13 (Test and release, App integrity, App signing). These are public; they are what
  `assetlinks.json` publishes:
  - app signing key: `A8:DA:8E:1A:34:79:3F:61:47:09:FA:7C:4E:EA:FC:AC:17:0B:69:8A:3B:25:C2:54:B3:3E:3D:1C:38:AA:72:A0`
  - upload key (EAS): `83:5E:38:2B:79:3A:D9:07:1C:78:89:76:69:8B:D9:E0:50:90:24:7A:AF:6A:17:EB:1B:17:8A:7D:53:A5:23:E8`
  - Done on 2026-11-13: `ANDROID_CERT_SHA256` holds both, signing key first, comma between, on the cPanel web app
    (`xcode-mgr-web`; Software, Setup Node.js App, Edit, Environment variables, then Save and Restart). The setting
    survives deploys. `/.well-known/assetlinks.json` answers 200 with both, and Google's Digital Asset Links API
    (`statements:list` for the site) returns both for `ke.co.priori.xcode`.
  - To do: the same setting on the cPanel web app for `xcode.stg.priori.co.ke`, so invitation links on stg open the
    staging build. Its `assetlinks.json` answered 404 on 2026-11-13.
- Advertising ID, after the upload: App content, Advertising ID, no.

## 3. iOS (App Store)

1. Build from a fresh clone (section 1, step 5): in `apps/mobile`, `eas build --platform ios --profile staging` from
   `develop` for TestFlight testers, `--profile production` from `master` for review. Sign in to Apple when asked and
   let EAS create the distribution certificate and provisioning profile.
2. Submit: `eas submit --platform ios --profile staging` (or `production`) uploads to TestFlight. The first run creates
   the App Store Connect record. To create the record yourself instead (after step 1): Apps, +, New App, iOS, the
   name, English (U.K.), bundle id `ke.co.priori.xcode`, SKU `xcode-fleet`, Full Access.
3. Set `IOS_APP_ID=<TeamID>.ke.co.priori.xcode` on both cPanel web apps (Team ID from developer.apple.com,
   Membership) and restart each. Check that `/.well-known/apple-app-site-association` answers 200 on both.
4. App Store Connect: listing, App Privacy (answers below), age rating, Pricing and Availability (Free, Kenya),
   copyright (`2026 Priori Technologies Limited`). App Review Information: sign-in required, the phone number as the
   user name, the PIN as the password, and the notes below. Pick a production build (never a staging one), then Add
   for Review.

## Listing

**Name:** XCODE Fleet, on both stores and under the icon (`expo.name` in `apps/mobile/app.json`). "XCode" alone reads
as Apple's Xcode, which Apple refuses as a trademark.

**Subtitle (Apple, 30) / short description (Google, 80):**
Vehicle revenue, costs and petty cash for your fleet.

**Description:**

> Record what each vehicle in your fleet earns and spends, from the road or the office.
>
> - Enter each day's revenue per vehicle and look back over the day or the week.
> - Record petty cash expenses for a manager's approval, and see what is above your limit or still to be paid back.
> - Keep working without a signal. Entries wait safely on the phone and are sent when you are back online.
> - See only the companies and vehicles your role allows. Administrators invite people by email and choose what each
>   person can see and do.
> - Sign in with your phone number and a PIN. A new phone is confirmed with a code before it is trusted.
>
> The app is for people whose organization uses the service. Your organization's administrator sends you an
> invitation.

**Keywords (Apple, 100):** fleet,matatu,revenue,vehicle,expenses,petty cash,transport,bookkeeping,sacco

**Category:** Business (Apple and Google).
**Support URL (Apple):** https://priori.co.ke
**Privacy policy URL:** https://xcode.mgr.priori.co.ke/privacy

**App Review notes (Apple) / App access (Google):**

> The app is for staff of organizations that use the service, so accounts are made by invitation. The login below
> opens "Demo Fleet", an organization with sample vehicles and records and no real data.
> Phone number: <the --phone given to review-account create>
> PIN: <from review-account create>
> Code, when the app asks to confirm a new phone: <from review-account create>
> Account deletion: More, Delete my account.

## Privacy answers

What the app and service handle, from the privacy policy. Nothing is used for tracking or advertising, nothing is sold
or shared, and everything travels encrypted.

| Data                                         | Apple App Privacy                               | Google Data safety                               | Purpose                               |
| -------------------------------------------- | ----------------------------------------------- | ------------------------------------------------ | ------------------------------------- |
| Name, email, phone number                    | Contact Info: Name, Email Address, Phone Number | Personal info: Name, Email address, Phone number | App functionality, account management |
| Revenue, expenses, petty cash entries        | Financial Info: Other Financial Info            | Financial info: Other financial info             | App functionality                     |
| Random id per installation, to trust a phone | Identifiers: Device ID                          | Device or other IDs                              | App functionality, security           |

- Apple: every row is Linked to the user, Not used for tracking.
- Google: every row is Collected, Not shared, Required, Encrypted in transit; users can ask for deletion (in the app
  and at the account deletion URL above).
- Not collected: location, contacts, photos, camera, health, browsing, crash or analytics data, advertising ids.

## Other declarations

- Ads: none. Target audience: 18 and over. Not a news, health, government or financial-services app (it keeps
  records; it does not move money or lend).
- Content rating (Google, IARC) and age rating (Apple): answer none to every content question; expect Everyone / 4+.
- Apple export compliance: already answered by the build.

## Screenshots

- iPhone: 6.9-inch, 1320 x 2868 portrait, 3 to 10. No iPad (`supportsTablet` is false).
- Android phone: 2 to 8, 16:9 or 9:16, each side 320 to 3840 px.
- Use the Demo Fleet so no real data appears: sign-in, Revenue (a week of entries), a revenue entry, Petty cash,
  the offline queue, More.
