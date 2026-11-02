# Deploying PetPop: the cloud on AWS, the studio in the shop

One codebase, three roles, chosen with `PETPOP_DEPLOY` in `.env` and started with `make up` (decisions 123 and 124):

| Role | Runs | Where |
| --- | --- | --- |
| `cloud` | the customer app (web, and the API the native apps and kiosks use), `/kiosk`, print exports (Stage F), `/sync` | AWS EC2, Singapore |
| `studio` | Studio, `/studio`, the GenAI worker (Tripo), the sync agent | a machine in the shop |
| `all` | everything on one box | `make dev`, demos, `make smoke-stack` |

Kiosks in the shop talk to the cloud, so every order lives in one place. The shop's machine only makes outgoing
connections to the cloud; nothing in the shop is reachable from the internet.

```
 phones (App Store, Play)  ─┐                         ┌─ CloudFront ── S3 (releases, previews)
 kiosks in the shop        ─┼─ https ─ CloudFront ─── EC2: Caddy ─ api (cloud) ─ worker-kiosk (Stage F)
 web browsers              ─┘                                  │        └─ RDS Postgres, Redis
                                                               │ /sync (bearer token, outgoing from the shop)
 shop machine: api (studio) + worker-studio ── Tripo API       │
   sync agent ─────────────────────────────────────────────────┘
   └─ pushes releases, pulls bespoke requests and returns their results, pulls print bundles to the printer folder
```

## What moves between them

The sync agent runs inside the studio's API process and makes one round every `PETPOP_SYNC_INTERVAL` seconds
(default 15). Each step is idempotent, and a round that cannot reach the cloud just logs and tries again.

- **Releases.** Studio packs a release as before; the agent uploads any bundle the cloud does not hold. The cloud
  checks the signature (both sides need the same `PETPOP_RELEASE_KEY`) and installs it, and kiosks switch within 30 s.
- **Bespoke requests.** A kiosk's "Make it unique" becomes a job on the cloud that the cloud never runs. The agent
  pulls it into Studio under the same job id (it shows up in the queue as `kiosk:<id>`, with the customer's contact),
  and when it is done sends the GLB, thumbnail and turntable back. The customer's result page and QR are the cloud's;
  Studio's result screen shows that link. A failure is reported back too.
- **Prints.** Each finished order's print bundle (with payments on, only once paid) is downloaded into the shop's
  `PETPOP_FULFIL_DIR/<ticket>_<job id>/`, where the print station picks it up, then acknowledged. A reprint from the
  kiosk's five-tap ops panel sends it to the shop again.

## The cloud on AWS

1. **Network and storage.** Region `ap-southeast-1`. An S3 bucket (private, block public access on). Optionally RDS
   Postgres 16 (`db.t4g.micro` is enough to start; RDS can be ARM, it is managed); otherwise the Compose postgres
   with EBS snapshots.
2. **The instance.** x86 (Blender's `bpy` has no Linux ARM wheel, so no Graviton): `m7i.large` (2 vCPU, 8 GB) to
   start, larger if exports queue. Amazon Linux 2023 or Ubuntu 24.04 with Docker and the Compose plugin. An IAM
   instance role allowing `s3:GetObject`, `s3:PutObject`, `s3:ListBucket` on the bucket. Security group: 80 and 443
   from anywhere (or from CloudFront's managed prefix list only), 22 from your own address. An Elastic IP and a DNS
   name for the origin, e.g. `origin.petpop.sg`.
3. **`.env` on the instance** (from `.env.example`):
   ```
   PETPOP_DEPLOY=cloud
   GENAI_PROFILE=mock                  # the cloud runs no GenAI stage; bespoke jobs run in the shop
   PETPOP_PUBLIC_URL=https://petpop.sg # what customers see in result links and QR codes
   PETPOP_TLS_DOMAIN=origin.petpop.sg  # Caddy gets a Let's Encrypt certificate for the origin
   PETPOP_SYNC_TOKEN=<long random>     # the same on the shop machine
   PETPOP_RELEASE_KEY=<long random>    # the same on the shop machine
   PETPOP_SECRET=<long random>
   PETPOP_STAFF_TOKEN=<kiosk ops PIN>
   KIOSK_BESPOKE=1
   DATABASE_URL=postgresql+psycopg://petpop:<pw>@<rds-endpoint>:5432/petpop   # or POSTGRES_PASSWORD for the Compose one
   S3_ENDPOINT=aws
   S3_BUCKET=<bucket>
   AWS_DEFAULT_REGION=ap-southeast-1
   ```
   Payment settings: the payments section below.
4. `make up`. It starts `api`, `worker-kiosk`, `redis` and `caddy` (plus `postgres` if `DATABASE_URL` is empty).
   `make down` stops it.
5. **CloudFront.** One distribution for `petpop.sg`, origin `origin.petpop.sg` over HTTPS:
   - `/api/*` and `/r/*`: caching disabled, all viewer headers, query strings and cookies forwarded (WebSockets work).
   - everything else (the web app's hashed assets, `/draco/`, `/fixtures/`): cached with the managed
     CachingOptimized policy.
   - an ACM certificate (us-east-1, as CloudFront requires) for `petpop.sg`.
   Library files and result previews are served by the API from S3 with signed links, so they pass through `/api/*`.
6. **The apps.** Build the native apps against the cloud: `VITE_API_ORIGIN=https://petpop.sg npm run build:native`
   (docs/LOCAL.md section 4). Kiosks open `https://petpop.sg/?mode=kiosk` once (or run a `VITE_MODE=kiosk` native build).

## Payments: HitPay (PayNow and cards)

The cloud takes payment for each order (decision 125). The customer pays on the order screen: PayNow shows a QR their
banking app scans; a card opens HitPay's hosted checkout (on a kiosk, a QR of the checkout to pay on their phone).
The figurine's export starts at once; its print bundle goes to the shop, and the result QR appears, once paid.

1. A HitPay business account (Singapore), PayNow and cards enabled. Start in the sandbox.
2. In the dashboard: an API key, and a webhook for payment requests pointing at
   `https://petpop.sg/api/v1/payments/hitpay/webhook`; note its salt.
3. On the cloud's `.env`:
   ```
   PETPOP_PAYMENTS=hitpay
   PETPOP_PRICE_SGD=39.00
   HITPAY_API_KEY=<key>                       # env only, never committed
   HITPAY_SALT=<webhook salt>
   HITPAY_API_URL=                            # empty = sandbox; https://api.hit-pay.com/v1 when you go live
   ```
4. Test in the sandbox with an order from the app; the webhook marks it paid (the app also asks HitPay while a payment
   is pending, so a missed webhook only delays it).

`PETPOP_PAYMENTS=fake` is the same flow with a "Simulate payment (test)" button and no money; the Playwright tests run
it. `off` (the default) skips payment: the shop takes it at the counter.

## Accounts and notifications

Customers sign in with Apple, Google, or a six-digit code sent to their email or phone (no passwords); a guest gives
an email or phone at checkout and may create an account with it there (decision 126). The cloud verifies Apple's and
Google's id tokens itself, so it only needs their public client ids. Codes and messages are written to the log
until a sender is switched on.

1. **Sign in with Apple** (Apple Developer account): enable the capability on the iOS App ID (the bundle id, e.g.
   `sg.petpop.app`); for the web, a Services ID (e.g. `sg.petpop.web`) with the domain `petpop.sg` and the return URL
   `https://petpop.sg/`. In Xcode, add the "Sign in with Apple" capability. `PETPOP_APPLE_CLIENT_IDS=sg.petpop.app,sg.petpop.web`.
2. **Google** (Google Cloud console, OAuth consent screen): OAuth client ids for Web (authorised origin
   `https://petpop.sg`), iOS (the bundle id) and Android (the package name and the signing key's SHA-1).
   `PETPOP_GOOGLE_CLIENT_IDS=<web>,<ios>,<android>`; build the app with `VITE_GOOGLE_IOS_CLIENT_ID=<ios>` and add the
   iOS client's reversed id as a URL scheme in `ios/App/App/Info.plist`.
3. **Push (Firebase, free):** a Firebase project with the iOS and Android apps; put `GoogleService-Info.plist` in
   `apps/customer/ios/App/App/` and `google-services.json` in `apps/customer/android/app/` (both from the Firebase
   console, not committed); upload an APNs auth key (Apple Developer, Keys) to Firebase; add the Push Notifications
   capability in Xcode. On the cloud: a service account key with the "Firebase Cloud Messaging API Admin" role at a
   path outside the repo, `PETPOP_PUSH=fcm`, `PETPOP_FCM_CREDENTIALS=/etc/petpop/fcm.json` (mount it into the
   containers).
4. **Email (Amazon SES, paid per message):** verify the `petpop.sg` domain (DKIM records), request production access
   (SES starts in a sandbox that only mails verified addresses), allow `ses:SendEmail` in the instance role.
   `PETPOP_EMAIL=ses`, `PETPOP_EMAIL_FROM=PetPop <hello@petpop.sg>`.
5. **SMS (Amazon SNS, paid per message):** in Singapore, alphanumeric sender ids must be registered with SGNIC's
   SMS Sender ID Registry first; then `PETPOP_SMS=sns`, `PETPOP_SMS_SENDER_ID=PetPop`, and `sns:Publish` in the
   instance role. SMS goes only when neither push nor email reached the customer.
6. **Privacy:** the app's privacy policy (App Store and Play listings) must name what is kept: name, email, phone,
   orders, device push tokens. Customers delete their account in the app (Account, Delete my account).

What is sent: "order confirmed" (when paid, or when placed with payments off), "ready to collect" (staff tap Ready on
the kiosk's staff panel) and "your one-off is ready" (when the studio returns a bespoke figurine).

## The studio in the shop

1. A machine with Docker (x86, or Apple Silicon under emulation) on the shop's network, near the printer.
2. **`.env`:**
   ```
   PETPOP_DEPLOY=studio
   GENAI_PROFILE=tripo                 # or tripo-manual (docs/MANUAL-MODE.md)
   TRIPO_API_KEY=<key>                 # env only, never committed
   PETPOP_CLOUD_URL=https://petpop.sg
   PETPOP_SYNC_TOKEN=<same as the cloud>
   PETPOP_RELEASE_KEY=<same as the cloud>
   PETPOP_SECRET=<long random>
   PETPOP_STUDIO_USERS=name:role:password;...
   POSTGRES_PASSWORD=<pw>
   S3_ACCESS_KEY=<minio user>
   S3_SECRET_KEY=<minio password>
   PETPOP_PUBLIC_URL=http://<shop machine LAN address>:8000   # result links for Studio's own one-offs
   ```
3. `make up` starts `api`, `worker-studio`, `postgres`, `redis` and `minio`. Studio is at `http://<machine>:8000/studio/`
   (the root redirects there). The print station watches the `fulfilment` volume (or bind-mount `PETPOP_FULFIL_DIR`).
4. Check the link: the API log shows a sync round every 15 s; a release published in Studio appears on the cloud's
   kiosks within a minute.

## Local check

`make test` includes `tests/server/test_deploy_roles.py`: a cloud and a studio backend side by side in one process,
the agent talking to the cloud through a test client (releases, bespoke round trip, prints, refused routes, an
unreachable cloud). `scripts/compose.sh config` prints the resolved Compose configuration for the current `.env`
without starting anything.
