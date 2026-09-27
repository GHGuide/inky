# Backup deck: 3 slides

Only for when the live demo can't run. Same look as the app: white or paper `#F7F6F3`, ink `#111110`, one coral `#E86F51` accent, Geist. One idea per slide. Real numbers only.

## 1 · Good listings go in days

- Title: **Tell it once.**
- Line: "Good listings go in days. Inky watches every 15 minutes; you only decide."
- The task in one line: a Dutch buyer with €200,000: where does a rented flat earn the most, with prices rising and buying easy?
- Result, big: **Łódź 32 · Bari 14 · Porto 0** homes that pass. Best: Łódź Śródmieście, 6.5% a year after costs.
- Small print: 17,836 listings read through Apify. Porto prices +17.8% a year (Eurostat 2026-Q1), but the rents don't pay.
- Say: "I told it once. This morning it sent me the best ones."

## 2 · How it works: AI where judgement is needed, compiled code everywhere else

A left-to-right strip of six steps, with the one AI step marked in coral:

1. **Describe**: one sentence, and it asks only what it can't guess.
2. **Research** (Apify): 17,836 listings, $17.49.
3. **Rules** (GLM-5.3, open weights): three rounds tested on the data, 15 → 70 → 46 homes, $0.15.
4. **Learn a site**: Tecnocasa had no actor. 10 steps, 1 GLM call, 8 steps became 1 request, published as its own Apify actor.
5. **Run** (n8n, built by Inky through the API): every 15 min, 5 Apify steps → compiled scoring → Telegram → Gmail draft. 0 AI calls.
6. **Repair**: an error → GLM-5.3 fixes one input → publish → rerun. 7.3 s.

Under the strip: "8 compiled windows: 96 flats in 19.7 s, 0 model calls. A click-by-click AI agent: 30 in 60 s, 5 calls."

## 3 · Proof, safety, and why OLX

- Left, proof: overnight 36 runs, 9,009 listings checked, 0 AI calls in the loop. The 23:30 repair (broken on purpose): "Changed searchType from 'sale' to the allowed enum value 'sprzedaz'", fixed and rerun.
- Middle, safety: never contacts anyone, only Gmail drafts. Asks before every draft. At most one fix an hour. A USD cap on every Apify step.
- Right, why OLX: Otodom and Imovirtual are OLX, a Prosus company. 32 of the 46 matches came from Otodom. Every approved draft is a qualified buyer enquiry.
- Footer: QR to github.com/GHGuide/inky · "Open source (MIT) · open models (GLM-5.3) · n8n is fair-code · Apify's platform is hosted".
