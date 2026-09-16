# SANGLEY owner operating guide

1. Open `/admin`, sign in with the credentials in `test_credentials.md`.
2. **Products**: edit a flavour, verify its facts, change prices/availability and paste hosted image URLs one per line. Images and descriptions update on the public site after Save. Product editor closes on successful save.
3. **Content**: change announcement, hero copy, story and shipping guidance. Add WhatsApp digits including country code (no + or spaces) to activate WhatsApp contact. Until then the public CTA uses the enquiry form.
4. **Structured content**: choose a section. Preserve field names and valid JSON. `null` means an unconfirmed price; `0` means a real zero price. Changes across sections publish together with Save & Publish.
5. **Reseller calculator**: approved `selling_price` and `cost_per_pack` produce gross margin before expenses. Leave cost null until agreed. Starter `price`, `quantity`, `margin`, `contents`, `products` and `offer` are editable independently.
6. **Reviews/UGC**: only add actual consented customer content. Reviews use name, product (exact product title), review, rating (optional, genuine), published. UGC uses image, caption, published. Nothing appears publicly without published=true.
7. **Toolkit**: inside reseller.resources add title, url, active. Set active only if the real resource is available.
8. **Leads**: use statuses to manage follow-up; records include contact, community details and campaign source. Consumer messages appear alongside reseller records but have separate type labels.
9. **Orders**: these are enquiries, not paid transactions. Contact the customer to confirm shipping and payment. Change status once actually contacted/confirmed/fulfilled.
10. **Export all data**: downloads portable JSON containing product, site content, enquiries and leads. This contains private business/customer information; handle it securely.

Current site: four 200g flavours at planned ₹149. 4/6/8 packs without configured box pricing total ₹596/₹894/₹1,192. No discounts are implied. Genuine customer moments are the best next addition to the public social section.