import { errStr, log } from "@/lib/log";

/**
 * Shopify checkout handoff (issue #11): create a cart on the live store with
 * the customer's design attached and hand back the checkout URL, so paying is
 * one tap from chat instead of waiting for the team on WhatsApp.
 *
 * Uses the Storefront API public token (Headless channel "Studio"
 * storefront) — it can only read products and create carts.
 */

const STOREFRONT_URL =
  "https://wkxmrc-00.myshopify.com/api/2026-01/graphql.json";

// Live variant ids per product/size (pulled from everything3dindia.com,
// 2026-07-17). Single uses the small-base variants — the studio doesn't
// offer the podium base. If the store's variants change, update these.
const VARIANT_GID: Record<string, Record<string, string>> = {
  single: {
    "13cm": "gid://shopify/ProductVariant/51362299969838",
    "15cm": "gid://shopify/ProductVariant/52319556829486",
    "18cm": "gid://shopify/ProductVariant/52319556862254",
  },
  couple: {
    "13cm": "gid://shopify/ProductVariant/52319542018350",
    "15cm": "gid://shopify/ProductVariant/52319542051118",
    "18cm": "gid://shopify/ProductVariant/52319542083886",
  },
  pet: {
    "13cm": "gid://shopify/ProductVariant/52319567118638",
    "15cm": "gid://shopify/ProductVariant/52319567151406",
    "18cm": "gid://shopify/ProductVariant/52319567184174",
  },
  family: {
    "13cm": "gid://shopify/ProductVariant/52319565775150",
    "15cm": "gid://shopify/ProductVariant/52319565807918",
    "18cm": "gid://shopify/ProductVariant/52319565840686",
  },
};

const CART_CREATE = `mutation($input: CartInput!) {
  cartCreate(input: $input) {
    cart { checkoutUrl }
    userErrors { field message }
  }
}`;

/**
 * Checkout URL for a standard product/size, with the design attached as
 * line-item attributes. Null for custom products, missing config, or any API
 * failure: the manual WhatsApp path always remains as fallback.
 */
export async function createCheckoutUrl(o: {
  product: string;
  size: string;
  baseText?: string;
  previewImageUrl: string;
  sessionId?: string;
}): Promise<string | null> {
  const token = process.env.SHOPIFY_STOREFRONT_TOKEN;
  const merchandiseId = VARIANT_GID[o.product]?.[o.size];
  if (!token || !merchandiseId) return null;

  const attributes = [
    { key: "Design preview", value: o.previewImageUrl },
    ...(o.baseText ? [{ key: "Base text", value: o.baseText }] : []),
    ...(o.sessionId
      ? [
          {
            key: "Design session",
            value: `https://studio.everything3dindia.com/s/${o.sessionId}`,
          },
        ]
      : []),
  ];

  try {
    const res = await fetch(STOREFRONT_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Shopify-Storefront-Access-Token": token,
      },
      body: JSON.stringify({
        query: CART_CREATE,
        variables: {
          input: { lines: [{ merchandiseId, quantity: 1, attributes }] },
        },
      }),
    });
    if (!res.ok) throw new Error(`storefront api ${res.status}`);
    const json = (await res.json()) as {
      data?: {
        cartCreate?: {
          cart?: { checkoutUrl?: string };
          userErrors?: { message: string }[];
        };
      };
      errors?: { message: string }[];
    };
    const errors = [
      ...(json.errors ?? []),
      ...(json.data?.cartCreate?.userErrors ?? []),
    ];
    if (errors.length > 0) throw new Error(errors[0].message);
    return json.data?.cartCreate?.cart?.checkoutUrl ?? null;
  } catch (err) {
    log("error", "checkout_create_failed", {
      product: o.product,
      size: o.size,
      err: errStr(err),
    });
    return null;
  }
}
