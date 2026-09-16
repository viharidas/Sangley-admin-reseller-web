# Shopify migration foundation

The current prototype does not call Shopify. It is deliberately structured for later mapping.

| SANGLEY field/entity | Shopify destination |
| --- | --- |
| product.handle | Product handle |
| title / description / vendor / category | Product title/body/vendor/type + collections |
| id | External ID metafield / migration reference |
| flavour / weight | Variant options and grams |
| sku / price / mrp | Variant SKU, price, compare-at price (only if genuine) |
| images / image_labels | Product media / alt text |
| ingredients / nutrition / storage / concept_images | Product metafields |
| seo_title / seo_description | SEO fields |
| available | Inventory policy/availability after actual stock integration |
| content.hero / announcement / story / FAQs | Theme sections / metaobjects |
| bundles | Bundle app rules and line-item properties |
| reseller kits/economics/resources | Metaobjects/metafields + appropriate app |
| leads and CRM status | Customers/tags/metafields or external CRM |
| enquiry orders | Draft orders only after explicit business approval; never import as paid orders |
| customer orders / addresses / profiles | Future Shopify customer accounts |

Use `/api/admin/export` to download versioned data and the mapping. All IDs are strings, all dates ISO UTC, media are URLs and monetary amounts are INR decimal values. Convert money to the destination API representation explicitly. Preserve each bundle selection and its per-product quantity/SKU. Theme token values and content are separate from React components, enabling reimplementation as Liquid sections. A real Shopify importer, operational app configuration and customer-auth migration are future tasks.