# Judge Q&A: short, honest answers

Say the number, then stop. If we don't know, say so.

**Isn't this just n8n's AI workflow builder?**
No. A builder writes a workflow from your prompt. Inky decides what the workflow should be from data first: it scrapes 17,836 listings through Apify, has GLM-5.3 propose rules, and tests them on every listing in three rounds. It learns a site that has no scraper and publishes it as an Apify actor. Then it writes both workflows through n8n's public API from a script that's in git, and it repairs them while they run. The workflow that runs every 15 minutes has no AI in it.

**How accurate are the yields?**
They're estimates, and the screen says so. The rent is the median €/m² of rental listings in the same neighbourhood: 486 rentals in Łódź Śródmieście, but only 26 in Bari Libertà. From that we subtract fixed shares per country: agency 9%, empty months 8%, upkeep about 1%, rent tax (8.5% in Poland, 21% in Italy, 25% in Portugal) and buying costs (3.5–8%). The price trend is per country (Eurostat, 2026-Q1), not per city. Łódź districts are approximated from coordinates. Treat it as a shortlist to visit, not a valuation.

**What if a site blocks you?**
Research goes through Apify Store actors, which deal with proxies and blocking. If a step fails, n8n's error path starts the repair: GLM-5.3 gets the error, the input and the actor's real input fields, and changes only that input. It does this at most once an hour, and it tells you on Telegram. If a site really blocks us, a human decides: switch to another actor, or re-learn the site. The Tecnocasa actor reads the site's own JSON feed, one request per page.

**What does it cost?**
The one-time research cost $17.49 of Apify for 17,836 listings, plus $0.15 of GLM for the rules. Learning Tecnocasa cost $0.02, and its test run was under $0.001. Each 15-minute run makes 0 AI calls. Each Apify step has a USD cap per run. At 40 listings per source, the four steps cost about $0.18 a run at the actors' listed prices [measured: fill in from Apify]. Every 15 minutes is the demo setting, about $17 a day. For a real buyer, once an hour costs about $4 a day, and twice a day under $0.40.

**Privacy?**
The keys stay in `.env` on the laptop. The app only answers on localhost. Speech is transcribed on the Mac with whisper.cpp. Inky never contacts anyone: approved homes become Gmail drafts, and you send them. Your plan text does go to GLM through OpenRouter, a hosted service. GLM-5.3 has open weights, so it could run locally instead. When you share an agent, your budget is never sent to the model.

**What's the business model?**
Not decided, honestly. The options: a hosted version with a subscription per watcher, with the code staying open; a marketplace for shared agents; or a partnership with portals. Every approved draft is a qualified buyer enquiry, which is what portals and agencies are paid for.

**Why Prosus / OLX?**
OLX, a Prosus company, owns Otodom and Imovirtual. 32 of our 46 matches are in Łódź, from Otodom. Inky turns a portal's listings into approved enquiries to agents. With OLX's own listing feed it wouldn't need to scrape at all.

**What's really autonomous?**
From one sentence and a few answers, Inky wrote and tested the rules itself (three rounds), built both n8n workflows through the API with no one touching n8n, and now runs every 15 minutes. When a step broke, it fixed the input, published the fix and reran in 7.3 s. You still do these things: set up the keys once, tap Save as draft, and send the email. The 23:30 failure was one we caused on purpose, as a test.

**What's mocked?**
The marketplace and the shared agents on it are a preview (hard-coded cards, labelled "Preview"). Sharing really writes the description and a link, but importing a shared agent into another n8n isn't built yet. We tested Laya, a small local model for choosing clicks, and it was only about 50% right on real pages, so we don't use it: clicks are replayed from the compiled program. Everything else is real: the research, rules, actor, race, both n8n workflows, the repair, Telegram, the Gmail drafts and voice.

**Why not a browser agent that clicks with an LLM?**
We raced one. 8 compiled windows read all 96 Bari Tecnocasa flats under €200,000 in 19.7 s with 0 model calls. A click-by-click GLM agent read 30 in 60 s with 5 model calls ($0.085). The compiled program is also repeatable and testable.

**What happens when a site changes its layout?**
Store actors are maintained by their authors. The repair fixes bad inputs and steps that return nothing. The Tecnocasa program uses the site's JSON feed, which changes less often than the page. If it breaks, re-learning costs one GLM call (about $0.02). Repairing a change in the data's shape is on the list, not built yet.

**Is scraping legal?**
It's public listing data, read at low volume through Apify, and we never contact anyone automatically. Each site has its own terms. A production version should use portal feeds or partnerships, which is part of why OLX matters.

**Does it work beyond housing?**
The pattern does: interview, research, learn a site, compile, watch, repair, ask. The scoring program (`inky.js`) is written for housing today. A new domain needs its own fields and metrics.

**Open source?**
Inky's code is open source (MIT), and GLM-5.3 has open weights. n8n is fair-code (source-available, self-hostable), and Apify's platform is hosted. So: open code and open models on top of two platforms, one of which you can self-host.
