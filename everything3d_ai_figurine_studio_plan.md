# Everything 3D AI Figurine Studio — Implementation Plan

## 1. Goal

Build a guided AI experience where customers can:

1. Chat with an AI assistant.
2. Upload reference photos.
3. Choose figurine options using visual UI cards.
4. Generate and revise AI previews.
5. See pricing and product options.
6. Continue to Shopify checkout.
7. Have the final Shopify order linked to the selected design session.

The AI experience will run separately from the existing Shopify storefront.

---

## 2. Recommended Product Architecture

```text
everything3dindia.com
└── Existing Shopify storefront

create.everything3dindia.com
└── New AI Figurine Studio hosted on Vercel
```

### Responsibility split

#### Vercel AI application

Vercel will host the customer-facing AI product layer:

- Guided chat
- Photo uploads
- Figurine configuration
- Custom option cards
- AI tool execution
- Preview generation workflow
- Preview revision workflow
- Pricing logic
- Design session storage
- Shopify cart creation
- Authentication
- Rate limiting and abuse protection

#### Shopify

Shopify will continue to handle:

- Product catalogue
- Variants
- Final pricing
- Discounts
- Customer information
- Shipping
- Tax
- Payments
- Checkout
- Orders
- Fulfilment

#### External image-generation provider

The actual image model will run through an external service such as:

- OpenAI
- Google
- fal
- Replicate
- A custom GPU inference service

Vercel will orchestrate the request but will not run heavy image-generation inference itself.

---

## 3. Repository Setup

The Shopify website may remain in its existing repository.

Create a separate repository for the AI application:

```text
everything3d-ai/
├── app/
│   ├── page.tsx
│   ├── api/
│   │   ├── chat/
│   │   ├── upload/
│   │   ├── generate-preview/
│   │   ├── revise-preview/
│   │   └── create-checkout/
│   └── design/
│       └── [sessionId]/
├── components/
│   ├── chat/
│   ├── style-picker/
│   ├── pose-picker/
│   ├── preview-card/
│   ├── order-summary/
│   └── auth-gate/
├── lib/
│   ├── agent/
│   ├── tools/
│   ├── prompts/
│   ├── image-generation/
│   ├── shopify/
│   ├── storage/
│   ├── database/
│   └── security/
├── public/
│   └── option-images/
├── package.json
└── README.md
```

A monorepo is not required initially.

Move to an `apps/` and `packages/` structure only when adding other applications, such as:

- Internal production dashboard
- Admin review application
- Background worker
- Shared design system
- Separate API service

---

## 4. Recommended Technology Stack

### Frontend

- Next.js App Router
- React
- TypeScript
- Tailwind CSS
- Vercel AI SDK UI
- `useChat` or equivalent AI SDK chat primitives

### Agent and tools

- Vercel AI SDK Core
- One multimodal language model
- Typed tools using Zod
- Structured figurine specification stored outside free-form chat

### Authentication

- Clerk
- Google login
- Passwordless email OTP
- No passwords

### Data

- Neon Postgres
- Drizzle ORM
- Private Vercel Blob storage

### Image generation

- External model provider
- Backend-controlled prompt templates
- Generated previews saved to private storage

### Commerce

- Shopify Storefront Cart API
- Shopify-hosted checkout
- Shopify order linked to the AI design session

### Deployment

- Vercel
- Custom domain: `create.everything3dindia.com`

---

## 5. Customer Experience

```text
Customer opens AI Figurine Studio
        ↓
Agent explains the process
        ↓
Customer chooses single, couple, pet, or group
        ↓
Customer selects size and style
        ↓
Visual cards show pose and outfit options
        ↓
Customer signs in
        ↓
Customer uploads reference photos
        ↓
Agent checks photo suitability
        ↓
Customer confirms figurine specification
        ↓
System generates a preview
        ↓
Customer accepts or requests a revision
        ↓
System calculates final price
        ↓
Customer clicks Buy
        ↓
Vercel creates a Shopify cart
        ↓
Customer completes Shopify checkout
```

---

## 6. UX Principle

Do not build this as a completely blank ChatGPT-style interface.

Use a guided configurator presented conversationally.

### Use chat for

- Explaining the process
- Handling unusual requests
- Answering questions
- Gathering custom instructions
- Explaining limitations
- Guiding customers when photos are unsuitable

### Use structured UI for

- Number of people
- Figurine type
- Style
- Pose
- Outfit
- Size
- Base options
- Base text
- Preview selection
- Revision confirmation
- Purchase actions

### Recommended screen layout

```text
┌──────────────────────────────────────────────┐
│ Everything 3D — Create Your Figurine         │
├───────────────────────────┬──────────────────┤
│                           │                  │
│ Chat and option cards     │ Order summary    │
│                           │                  │
│ Uploads and previews      │ Type             │
│                           │ Style            │
│                           │ Size             │
│                           │ Base             │
│                           │ Price            │
│                           │                  │
└───────────────────────────┴──────────────────┘
```

On mobile, the order summary can appear as a collapsible drawer.

---

## 7. Structured Figurine Specification

Do not rely on extracting the order configuration from chat after payment.

Maintain a structured specification throughout the session.

```ts
type FigurineSpecification = {
  productType: "single" | "couple" | "pet" | "group";
  numberOfPeople: number;
  style: "animated" | "bobblehead" | "semi-realistic";
  size: "13cm" | "18cm";
  pose?: string;
  outfits: Array<{
    subjectId: string;
    description: string;
    colors: string[];
  }>;
  base: {
    included: boolean;
    shape?: string;
    text?: string;
  };
  customInstructions?: string;
  selectedPreviewId?: string;
};
```

The frontend and agent should update the same structured state.

---

## 8. Agent Tools

The AI should not have unrestricted access to arbitrary backend actions.

Give it a narrow set of typed tools:

```text
analyseUploadedPhotos
showFigurineTypeOptions
showStyleOptions
showPoseOptions
showOutfitOptions
updateFigurineSpecification
generateFigurinePreview
reviseFigurinePreview
calculatePrice
createShopifyCart
requestHumanAssistance
```

### Important rule

The agent should collect structured choices.

Your backend should generate the final image prompt using controlled templates.

Do not let the customer or language model freely construct arbitrary image-generation prompts.

---

## 9. Custom UI Inside Chat

Each tool result may render a dedicated React component.

Examples:

### Style picker

```text
Choose your figurine style

[ Animated ]
[ Bobblehead ]
[ Semi-realistic ]
```

Each option should include:

- Example image
- Name
- Brief description
- Select button

### Preview card

```text
Preview 2

[ Generated figurine image ]

[ Select this design ]
[ Request changes ]
[ Generate another ]
```

### Purchase card

```text
13 cm Couple Figurine
Selected preview: Preview 2
Base text: Apoorv & Juthika
Price: ₹2,999

[ Continue to checkout ]
```

---

## 10. Authentication and Access Gating

### Recommended login timing

Do not require login immediately when the page opens.

Allow anonymous users to:

- Browse examples
- Learn how the process works
- Chat within a limited allowance
- Choose basic product options

Require login before:

- Uploading personal photos
- Generating a preview
- Revising a preview
- Saving a design
- Creating a checkout

### Login methods

Use Clerk with:

1. Continue with Google
2. Continue with email code

Avoid passwords.

Phone OTP can be added later if repeated-account misuse becomes a serious problem.

---

## 11. Abuse Prevention

Login alone is not enough.

Use several layers.

### Layer 1: Narrow product scope

Do not expose a generic image-generation prompt box.

The system should only create 3D figurine previews using approved options and uploaded reference images.

### Layer 2: Bot protection

Protect expensive routes using Vercel BotID:

```text
/api/upload
/api/generate-preview
/api/revise-preview
/api/create-checkout
```

### Layer 3: IP rate limits

Suggested starting limits:

```text
Chat:
20 messages per IP per hour

Uploads:
5 upload sessions per IP per day

Image generation:
3 attempts per IP per day
```

### Layer 4: User quotas

Suggested starting limits:

```text
Authenticated user:
1 free preview
1 free revision
Hard daily generation cap
```

Store quotas in the database.

Do not trust browser cookies or frontend state for enforcement.

### Layer 5: Economic gate

Recommended model:

```text
After login:
- 1 free watermarked preview
- 1 free modification

After that:
- ₹99–₹199 design deposit
- Deposit adjusted against final purchase
```

This is likely to be more effective than placing severe limits on inexpensive text chat.

### Layer 6: Watermarking

Free previews should be:

- Reduced resolution
- Watermarked with Everything 3D
- Unsuitable for unrelated commercial reuse

Keep the clean production reference private.

---

## 12. Database Model

Suggested tables:

### Users

```text
id
auth_provider_user_id
email
free_generations_used
paid_generation_credits
suspended_at
created_at
updated_at
```

### Design sessions

```text
id
user_id
status
figurine_specification_json
selected_preview_id
shopify_cart_id
shopify_order_id
created_at
updated_at
```

### Uploaded assets

```text
id
design_session_id
user_id
blob_path
asset_type
expires_at
created_at
```

### Generated previews

```text
id
design_session_id
generation_number
blob_path
prompt_version
generation_provider
generation_cost
status
created_at
```

### Generation events

```text
id
user_id
design_session_id
ip_hash
event_type
status
model_cost
created_at
```

### Payments or credits

```text
id
user_id
design_session_id
credit_type
amount
payment_reference
created_at
```

---

## 13. Photo and Preview Storage

Use private Vercel Blob storage.

Suggested structure:

```text
sessions/{sessionId}/source/front.jpg
sessions/{sessionId}/source/side.jpg
sessions/{sessionId}/previews/preview-1.png
sessions/{sessionId}/previews/preview-2.png
```

### Security requirements

Every stored file must be linked to:

- Authenticated user ID
- Design session ID
- Asset type
- Expiry date

Every read or modification request must verify that the current user owns the design session.

Never trust a `designSessionId` received from the frontend without checking ownership.

### Retention

Suggested default:

- Delete abandoned source photos after 14–30 days.
- Keep purchased design assets for the required production and support period.
- Provide a visible “Delete my photos” action.

---

## 14. Image Generation Workflow

```text
Customer confirms specification
        ↓
Backend checks authentication
        ↓
Backend checks BotID
        ↓
Backend checks IP and user quota
        ↓
Backend validates uploaded photos
        ↓
Backend creates controlled prompt
        ↓
Backend calls image provider
        ↓
Result saved to private Blob
        ↓
Preview metadata saved to Postgres
        ↓
Preview card rendered in chat
```

### Prompt construction

Use versioned prompt templates:

```text
promptVersion: figurine-preview-v1
```

The prompt should incorporate:

- Number of subjects
- Recognizable facial features
- Selected style
- Selected pose
- Outfit choices
- Base configuration
- Solid-color requirements
- 3D-printability requirements
- White background
- No unwanted text or logos

Do not allow the language model to silently change manufacturing constraints.

---

## 15. Shopify Integration

The AI application will create a Shopify cart after the customer selects a preview.

The cart should include:

- Correct Shopify variant
- Quantity
- Design session ID
- Figurine type
- Size
- Selected preview ID
- Base text
- Other production notes

Example custom attributes:

```json
{
  "design_session_id": "fig_28Hfw91",
  "figurine_type": "couple",
  "size": "13cm",
  "style": "animated",
  "base_text": "Apoorv & Juthika",
  "selected_preview_id": "preview_2"
}
```

The final checkout remains on Shopify.

### Important rule

Do not put full customer photo URLs into public Shopify line-item data.

Store only an immutable design session ID.

The internal production system can use that ID to retrieve the authorized assets.

---

## 16. Login and Shopify Accounts

For v1, keep authentication systems separate:

```text
AI application login → Clerk
Shopify checkout      → Shopify
```

Do not try to unify customer identity systems initially.

Later, Shopify Customer Accounts can be considered if customers need:

- Previous figurine designs
- Reorders
- Unified order history
- Shipping status
- Saved addresses
- A single account across the storefront and AI studio

---

## 17. Deployment Setup

### Vercel project

Deploy the `everything3d-ai` repository as a Vercel project.

### Domain

Configure:

```text
create.everything3dindia.com
```

Point the subdomain DNS record to Vercel.

### Shopify changes

Add prominent calls to action on the existing website:

```text
Create Your Figurine
Try the AI Figurine Studio
See Your Figurine Preview
```

These buttons should open:

```text
https://create.everything3dindia.com
```

---

## 18. Environment Variables

Suggested environment variables:

```text
DATABASE_URL

CLERK_SECRET_KEY
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY

BLOB_READ_WRITE_TOKEN

SHOPIFY_STORE_DOMAIN
SHOPIFY_STOREFRONT_ACCESS_TOKEN
SHOPIFY_API_VERSION

IMAGE_PROVIDER_API_KEY
IMAGE_PROVIDER_MODEL

AI_MODEL_API_KEY
AI_MODEL_NAME

APP_URL
SHOPIFY_CHECKOUT_RETURN_URL

FREE_PREVIEW_LIMIT
FREE_REVISION_LIMIT
DESIGN_DEPOSIT_AMOUNT
```

Keep all secret credentials server-side.

---

## 19. Suggested MVP Scope

### Include in v1

- Separate Next.js application
- Vercel deployment
- Subdomain
- Google and email OTP login
- Guided chat
- Single and couple figurines
- Two or three styles
- Visual style cards
- Photo upload
- Structured specification
- One preview generation
- One revision
- Watermarking
- Shopify cart creation
- Basic rate limits
- Database-backed quotas
- Private image storage
- Human assistance fallback

### Do not include in v1

- Multi-agent architecture
- Vercel Eve
- Fully autonomous ordering
- Phone OTP
- Unified Shopify and AI login
- Large internal dashboard
- Complex credit wallet
- Arbitrary image-generation prompts
- GPU inference hosted directly on Vercel
- Serving the app under `everything3dindia.com/create`
- Automated 3D mesh generation
- Automated printability approval without human review

---

## 20. Implementation Phases

## Phase 1: Foundation

- Create new repository.
- Set up Next.js and TypeScript.
- Deploy basic app to Vercel.
- Connect `create.everything3dindia.com`.
- Add shared branding.
- Create initial database schema.
- Add private Blob storage.

### Deliverable

A deployed shell application with working database and storage connections.

---

## Phase 2: Guided Configurator

- Build chat interface.
- Add persistent order summary.
- Add structured figurine specification.
- Add image option cards.
- Add single/couple flow.
- Add style, pose, size, and base choices.
- Add server-side agent tools.

### Deliverable

A guided configurator that reaches a completed figurine specification without generating an image.

---

## Phase 3: Login and Security

- Add Clerk.
- Enable Google login.
- Enable email OTP.
- Gate uploads and preview generation.
- Add BotID.
- Add IP rate limits.
- Add database-backed user quotas.
- Add ownership checks.

### Deliverable

A secure authenticated workflow for expensive actions.

---

## Phase 4: Image Generation

- Integrate one image-generation provider.
- Create controlled prompt templates.
- Add photo suitability checks.
- Generate preview images.
- Save previews privately.
- Add preview cards.
- Add one revision workflow.
- Add watermarking.

### Deliverable

A user can upload photos and receive a controlled figurine preview.

---

## Phase 5: Shopify Checkout

- Map figurine selections to Shopify variants.
- Create Shopify carts through the Storefront API.
- Add design session attributes.
- Redirect to Shopify checkout.
- Verify that completed orders retain the design session ID.

### Deliverable

A preview can be converted into a paid Shopify order.

---

## Phase 6: Operations and Analytics

- Add an internal session lookup page.
- Show source photos and selected preview.
- Track conversion funnel.
- Track generation cost per customer.
- Track failures and abandoned sessions.
- Add manual suspension and credit controls.
- Add asset-retention jobs.

### Deliverable

The team can fulfil orders and understand costs and conversion.

---

## 21. Key Metrics

Track at minimum:

```text
Landing page visits
Chat started
Configuration completed
Login completed
Photos uploaded
First preview generated
Revision requested
Preview selected
Checkout opened
Purchase completed
Average image-generation cost
Average generations per paid order
Abuse-block rate
Photo upload failure rate
Preview generation failure rate
```

The most important business metric is:

```text
Total AI generation cost per completed Shopify order
```

---

## 22. Final Recommended Architecture

```text
Shopify storefront
everything3dindia.com
        │
        │ Create Your Figurine
        ▼
Next.js AI application on Vercel
create.everything3dindia.com
        │
        ├── Vercel AI SDK
        ├── Custom React UI
        ├── Clerk authentication
        ├── BotID and rate limits
        ├── Neon Postgres
        ├── Private Vercel Blob
        └── External image provider
                 │
                 ▼
           Generated preview
                 │
                 ▼
        Shopify Storefront Cart API
                 │
                 ▼
           Shopify checkout
                 │
                 ▼
          Shopify order linked by
             design_session_id
```

---

## 23. Core Decisions

1. Keep Shopify in its current repository.
2. Create a separate repository for the AI application.
3. Host the complete AI product layer on Vercel.
4. Use `create.everything3dindia.com`.
5. Use the Vercel AI SDK rather than Eve for v1.
6. Use structured UI alongside chat.
7. Require login before upload or image generation.
8. Support Google login and email OTP.
9. Give one limited free preview and one revision.
10. Add a refundable design deposit if generation abuse or cost becomes significant.
11. Keep customer images private.
12. Use an external image-generation provider.
13. Keep Shopify responsible for payment and final orders.
14. Link Shopify orders to AI sessions using `design_session_id`.
15. Do not build a generic public image generator.
