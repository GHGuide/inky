# Learning report

What learning does on the kinds of pages people meet, and on real practice sites with a small local model. Written
2 October 2026, branch `learning-tests`.

## How to run it

```sh
python -m unittest tests.test_learning        # 42 tests, about 3 minutes, no network, a scripted model
python -m tests.journeys learning             # real sites with gemma3:12b from Ollama, about 15 minutes
INKY_LEARN="quotes.toscrape.com" python -m tests.journeys learning      # one site only
INKY_JOURNEY_DIR=/tmp/scratch INKY_JOURNEY_PORT=9201 INKY_LOCAL_SITE_PORT=9210 python -m tests.journeys learning
```

`tests/learn_site.py` is a local shop with one page per archetype (run `python -m tests.learn_site 8770` to look
around). `tests/test_learning.py` drives the real browser with a scripted model (`Plan`): it does its steps in
order, then asks to read the results. Every archetype is learned, then replayed twice with a model that fails if it
is called. Both replays must read the same items, each with its own name (never "View" or "Details") and a price
that parses.

## Archetypes: before and after

"Before" is these tests run against the code this branch started from (`2429c47`).

| Archetype | Test | Before | After |
|---|---|---|---|
| GET search form, 3 pages | `test_get_search_form` | pass | pass |
| `max_pages`, rules on the results | `test_max_pages_and_rules` | pass | pass |
| Search box with no button (model presses Enter) | `test_search_box_with_no_button` | pass | pass |
| Search typed but never sent (Enter pressed for it) | `test_unsent_search_gets_enter` | pass | pass |
| ASP.NET: one POST form around the page, newsletter box in the footer | `test_aspnet_post_form_searches_without_asking` | **fail**: asked approval to search | pass |
| ASP.NET with a sign-in box in the header; a contact form with its own `<header>` | `test_aspnet_form_parts` | **fail**: the search button counted as signing in | pass |
| Category links instead of search | `test_category_links_instead_of_search` | pass | pass |
| Next link | (in the search tests) | pass | pass |
| Only page numbers (1 2 3 4) | `test_numbered_pages` | **fail**: one page read | pass |
| Next link that is only an arrow (› » →) | `test_next_page_arrows` | **fail**: not followed | pass |
| Load more button | `test_load_more_button` | **fail**: 25 bikes read as 55 | pass |
| Infinite scroll | `test_infinite_scroll_reads_what_is_shown` | pass (first 10 only) | pass (first 10 only) |
| Next page that takes a second | `test_a_next_page_that_takes_a_second` | pass | pass |
| Prices: `€ 1.234,56`, `$1,234.56`, `£12`, Free, from €99, a range, struck-out old price, discount badge | `test_prices`, `test_parse_num` | **fail**: Free unread and failing "≤ 100"; sale card read at the old price | pass |
| Results without prices | `test_results_without_prices` | pass | pass |
| Results in a table | `test_results_in_a_table` | **fail**: "price" was the name cell (300 from "C300") | pass |
| A table without links (hockey teams) | `test_a_table_without_links` | **fail**: no list found | pass |
| Cards whose only link says Details / Dettagli / View | `test_titles_never_details_or_view` | **fail**: titled "View" when there is no heading | pass |
| Results that share links (quotes and their tags) | `test_shared_links_dont_merge_results` | **fail**: 29 quotes stored as 10, titled by tags | pass |
| A reading step learned before, on shared links | `test_a_reading_step_on_shared_links_still_keeps_results_apart` | **fail** | pass |
| One sponsored copy of a result | `test_a_sponsored_copy_doesnt_cost_the_others_their_links` | **fail**: counted twice | pass |
| Hacker News: story rows with vote and user rows between | `test_story_rows_with_vote_and_user_rows_between` | **fail**: a model answering "none fits" left nothing to read | pass |
| Links named only by `aria-label="Navigation subcategory"` | `test_links_are_named_by_what_they_say` | **fail** | pass |
| Cookie wall over the page | `test_cookie_banner_over_the_page` | pass | pass |
| Results that come 1.5 s after the page | `test_results_that_come_after_the_page` | **fail**: learning gave up | pass |
| HTTP redirect, JavaScript redirect | `test_redirects` | pass | pass |
| 404 (a shop's error page with its whole menu) | `test_broken_address_stops_at_once` | **fail**: about 10 AI calls, wrong reason | pass: 0 AI calls |
| Very slow page (3 s) | `test_slow_page` | pass | pass |
| Home feed, sell / log in / post-an-ad links | `test_home_feed_sell_and_log_in_are_refused` | pass | pass |
| Category menu with counts | `test_category_menu_is_not_results` | pass | pass |
| Wrong kind of results (boys' bikes for e-bikes) | `test_wrong_kind_of_results_are_refused` | pass | pass |
| A few featured items, the category one link away (webscraper.io) | `test_featured_items_beside_the_category_link` | **fail**: read the 3 featured items | pass |
| Opening one listed result | `test_opening_one_result_is_no_step` | **fail**: learned "click this story" | pass |
| A search that finds nothing (hockey) | `test_a_search_that_finds_nothing_is_undone` | **fail** | pass |
| The model retyping that search forever | `test_a_search_that_found_nothing_isnt_tried_again_and_again` | **fail**: up to 48 AI calls | pass: ≤ 8 |
| The same mistake again and again | `test_the_same_mistake_three_times_gives_up_soon` | **fail**: 11+ AI calls | pass: ≤ 5 |
| Sign-in wall | `test_sign_in_wall_stops_and_types_nothing` | **fail**: typed a made-up email first | pass: stops as sign-in, nothing typed |
| Robot check; a site that refuses bots | `test_robot_check_and_bot_refusal_stop_with_no_model` | pass | pass |
| Renamed button: one model call repairs it, then free again | `test_renamed_button_is_repaired_with_one_call` | pass | pass |
| A step that can't be fixed stops (unsure, or sure but the wrong kind of control) | `test_step_that_cant_be_fixed_stops` | pass | pass |
| Engine: a repair is kept only when it finds results | `test_a_repair_is_kept_only_when_it_finds_results` | pass | pass |
| Engine: 29 quotes stored as 29; a second run finds none new, with 0 AI calls | `test_quotes_are_stored_one_each_and_a_second_run_finds_none_new` | **fail**: 6 stored | pass |

42 tests: 24 failed before, all 42 pass now. The full unit suite passes.

## Real sites, gemma3:12b

One learn and two runs per site, on the final code. The job sentence goes through the app's draft (one more AI
call, not counted below), like the New bot screen. "Check" is the run the app makes right after learning.

| Site | Job, as typed (rules the draft made) | Learned | AI calls to learn | Read / pass the rules | Fits the job | Titles, prices | AI calls: check, run 1, run 2 | New: check, run 1, run 2 | Time: learn + check, then each run | Steps learned |
|---|---|---|---|---|---|---|---|---|---|---|
| books.toscrape.com | “Find books under £20 on books.toscrape.com” (price under £20) | yes | 1 | 60 / 14 | yes: books, 3 pages | full titles, 60/60 priced | 0, 0, 0 | 14, 0, 0 | 12 s, then 2 s | Read 20 results; Next page |
| quotes.toscrape.com | “Collect the quotes on quotes.toscrape.com” (none) | yes | 2 | 30 / 30 | yes: 30 quotes, 3 pages | the quote's words, none generic | 0, 0, 0 | 30, 0, 0 | 33 s, then 2 s | Read 10 results; Next page (Next →) |
| scrapethissite.com forms | “Find hockey teams with more than 40 wins” (text > 40) | yes | 5 | 50 / 50 | yes: teams, 2 pages* | team names, 50 distinct | 0, 0, 0 | 50, 0, 0 | 87 s, then 3 s | Read 25 results; Next page |
| webscraper.io static | “Find laptops under $500” (price under $500) | yes | 5 | 18 / 4 | yes: laptops, 3 pages | full names, 18/18 priced | 0, 0, 0 | 4, 0, 0 | 90 s, then 5 s | Decline cookies; Computers; Laptops; Read 6 results; Next page (») |
| webscraper.io allinone | “Find laptops under $500” (price under $500) | yes | 5 | 117 / 38 | yes: all laptops | full names, 117/117 priced | 0, 0, 0 | 38, 0, 0 | 90 s, then 3 s | Accept cookies; Computers; Laptops; Read 117 results |
| news.ycombinator.com | “Tell me new Hacker News stories about AI” (mentions AI) | yes | 4 | 30 / 3 | yes: front-page stories | story titles | 0, 0, 0 | 3, 0, 0 | 117 s, then 0.5 s | Read 30 results |
| local test site | “Find flats in Bari under 150000 euro” (≤ €150000, mentions Bari) | yes | 4 | 27 / 14 | yes: flats in Bari | listing titles, 27/27 priced | 0, 0, 0 | 14, 0, 0 | 36 s, then 5 s | Accept cookies; Type Bari; Search; Read 10 results; Next page (Avanti) |

\* On scrapethissite.com the "»" link on the first page (with no `page_num`) leads to `page_num=1`, the same page
again. A run reads it, finds nothing new, and goes on to page 2. That's the site, not Inky. Every run is free,
and the second run finds nothing new on every site.

Before these fixes, the same journey with the same model gave:

| Site | Before |
|---|---|
| books.toscrape.com | learned (1 AI call) |
| quotes.toscrape.com | not learned, 5 AI calls: titles were tags, so the model said "these are topics, not quotes" |
| scrapethissite.com | not learned, 13 AI calls: searched "hockey", then clicked Search ten times |
| webscraper.io static | "learned" the 3 random featured items on the Computers page (a tablet among them), with "Click Computers" saved three times |
| webscraper.io allinone | "learned" the 3 featured items; another run got stuck (8 AI calls) |
| news.ycombinator.com | not learned, 12 AI calls (the model picked "no list fits"); another run learned "click this AI story", and both runs after it failed |
| local test site | learned (4 AI calls) |

Runs vary from one try to the next with a 12B model. The draft also varies: one run of the books job came back
with no £20 rule (all 60 passed). That's the draft, not learning.

## Bugs found and fixed

Each fix is its own commit with a unit test.

| What a person saw | Root cause | Commit |
|---|---|---|
| An ASP.NET site's search asked for approval, or stopped for a sign-in | One POST form wraps the page, so a footer email box made every button "send personal data", and a header password box made it "sign in". Now, in a page-wide form (`__VIEWSTATE`, or `main` / `nav` inside), only the controls next to the button count | `8bfc9dc`, `66a79e4` |
| A sale item missed a price limit; Free items were dropped by "under £20" | The price selector matched the struck-out `<del>` price first; "Free" has no number | `65c1282` |
| A table's "price" was a number in the name | A `<td>` with no class fell back to the first `td` | `c0ebc65` |
| Results titled "View"; 29 quotes stored as a handful, titled by tags | Generic link text was used when there was no heading; a shared link (tag, author) was taken as each result's own and used as its key | `bed1c76`, `8b29e0b`, `7c44169` |
| "Load more" counted 25 bikes as 55 | Every press re-reads the earlier ones | `15d9589` |
| Sites with only page numbers, or only "›", read one page | No fallback for page numbers; the next-page pattern ended in `\b`, which a lone arrow never matches | `9790cbc`, `37a840c` |
| Lists that arrive after the page were missed | Learning and replay read straight after DOMContentLoaded + 250 ms | `86bc0d1` |
| A wrong address spent about 10 AI calls | The HTTP status was never looked at | `9ccaf4c` |
| A sign-in wall got a made-up email typed into it | Only the password box was guarded | `65fd29d` |
| The hockey table wasn't seen at all | Lists had to have links in most rows | `ecd137a` |
| webscraper.io read featured items, saved "Click Computers" ×3 | Category links were all named by their `aria-label` "Navigation subcategory", so the model couldn't pick Laptops. A link to the current page counted as a step. A few items were read even with the right category one link away | `960c0b5`, `0b440d6` |
| A model repeating itself burned 13 calls | Only "10 replies without a step" stopped it | `8662523` |
| HN learned nothing | Asked to pick a list, the model said "none fits" because not every story is about AI; lists of vote and user rows were offered as options | `2ce70ff` |
| HN learned "click this AI story", then every run failed | Opening one of the listed results was accepted as a step | `e579100` |
| Hockey: an empty search was learned, then retyped forever | Nothing noticed that a search had emptied a page; the drafted goal "Identify …" didn't count as a finding job, so the finding guards were off; each retype counted as progress | `b61be65`, `ccd67ac`, `d0c1027` |
| A win rate (0.55) shown as each team's price | A bare decimal counts as a price; in a table it now needs a currency | `ccd67ac` |
| "More than 40 wins" passed every team | The rule became `text > 40` and compared the first number in the row (the year). Now it's kept and reported as unchecked | `7863cf4` |

## Not fixed, and why

- **Infinite scroll** reads only what the page shows first (10 items here). Scrolling to load more would mean a new
  replay step type. For "what's new" jobs the newest items come first anyway.
- **Rules on a table column** ("more than 40 wins") can't be checked: the draft only knows the fields price, size,
  title and text, and tables aren't read column by column. The bot now says it couldn't check the rule instead of
  pretending.
- **Hacker News "More"** isn't followed (one page of 30). A bare "More" is too often "read more" or "more
  categories" to treat as a next page.
- **A 12B model still varies** from one try to the next. These fixes make the learner catch its mistakes, but a run can
  still take an odd path. The `five` release gate wasn't run here: it searches the web for sites and visits
  sites other than the practice ones.
