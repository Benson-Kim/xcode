# App Store and Play Store release

App id `ke.co.priori.xcode` on both stores (fixed for good after the first release). Store builds talk to
`https://api.xcode.mgr.priori.co.ke` and verify invitation links against `https://xcode.mgr.priori.co.ke`.

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

## 1. Server, before any submission

The reviewers sign in to the live instance, so it must run the release these builds expect and hold the review login.

1. Merge PR #15 (`feat/review-organization`) into `develop`, then `develop` into `master`. CI deploys `master` to the
   migration instance.
2. Once, on the droplet: `xcode-migration-instance/droplet/9-auto-update.sh`. Check that
   https://api.xcode.mgr.priori.co.ke/release answers with the `master` commit.
3. `review-account create` on the droplet. It makes the Demo Fleet and prints the review phone number and PIN. Run it
   again only for a new submission (each run prints a new PIN).
4. Sign in with that login on a freshly installed build, on a phone that has never used it, before you give it to a
   reviewer.
5. Build only from a clean checkout of `master`. EAS uploads uncommitted files too, so a build from a tree with work in
   progress ships that work.

## 2. Android (Google Play)

1. Play Console, Create app: name (see Listing), default language English (United Kingdom), App, Free.
2. Build: `cd apps/mobile`, then `eas build --platform android --profile production`.
3. The first upload is by hand: Testing, Internal testing, Create release, upload the `.aab` from the EAS build page.
   Accept Play App Signing.
4. App integrity, App signing: copy both SHA-256 fingerprints (app signing key and upload key). Set
   `ANDROID_CERT_SHA256=<signing>,<upload>` on the cPanel web app (`xcode-mgr-web`) and restart it. Check that
   https://xcode.mgr.priori.co.ke/.well-known/assetlinks.json answers 200.
5. Fill App content (answers below), the store listing, and send the internal release out. Add testers by email.
6. Later builds: `eas submit --platform android --profile production` sends a draft to Internal testing. It needs a
   Google service account key, added once with `eas credentials` (Android, Google Service Account) so it stays on
   EAS and never in this repository.
7. Promote Internal, then Closed or Production, from Play Console. A personal developer account must first run a
   closed test with 12 testers for 14 days; an organization account does not.

## 3. iOS (App Store)

1. Build: `cd apps/mobile`, then `eas build --platform ios --profile production`. Sign in to Apple when asked and let EAS
   create the distribution certificate and provisioning profile.
2. Submit: `eas submit --platform ios --profile production`. The first run creates the App Store Connect record and
   uploads to TestFlight.
3. Set `IOS_APP_ID=<TeamID>.ke.co.priori.xcode` on the cPanel web app (Team ID from developer.apple.com, Membership)
   and restart it. Check that https://xcode.mgr.priori.co.ke/.well-known/apple-app-site-association answers 200.
4. App Store Connect: listing, App Privacy (answers below), age rating, pricing (Free), App Review Information with
   the review login and the notes below, then Add for Review.

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
> Phone number: <from review-account create>
> PIN: <from review-account create>
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
