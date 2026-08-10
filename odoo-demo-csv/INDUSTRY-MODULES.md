# Industry modules

Odoo ships one module per trade. Installing it configures the database *for that
business* — the apps it needs, its reports, its way of selling — and Odoo pulls
the whole dependency chain in behind it. So the industry module is the only extra
name `install-modules` needs.

Pick the **one** module closest to the target's trade and add it to that call.
The headings narrow the list; each description is written to separate the
neighbours that share a word (`bakery` and `cake_shop`, `hotel` and
`guest_house`, `real_estate` and `industry_real_estate`).

No module fits? Install the run's base modules alone and say so in one line. A
trade forced into the wrong industry module configures the database against the
demo.

## What the module brings with it

It arrives with its own sample records — products, partners, knowledge articles,
a configured point of sale. That is the point of it, and it is why the database
is not empty when you start importing: your CSV rows land *beside* those
records. Ground truth is unchanged — everything *you* write still traces back to
the target's own site.

## Retail

- `agriculture_shop` — feed, seed and farm supplies sold to growers.
- `art_craft` — art materials over the counter, plus paid workshops.
- `automobile` — a spare-parts counter serving garages and drivers, not a dealership.
- `bakery` — bread and pastry baked on site, sold over the counter.
- `beauty_parlor` — beauty treatments by appointment, products sold alongside.
- `bike_shop` — bicycle sales with a repair workshop behind them.
- `bookstore` — books over the counter, loyalty and publisher reordering.
- `cake_shop` — cakes and patisserie made to order and collected, rather than baked for the counter.
- `candy_shop` — confectionery sold loose or packaged.
- `clothing_boutique` — apparel, with sizes and colours as variants.
- `cosmetics_store` — skincare and make-up, with treatments in store.
- `electronic_store` — consumer electronics, with repairs and a warranty desk.
- `florist` — cut flowers and arrangements, counter trade plus event orders.
- `fmcg_store` — a grocery store: everyday goods, barcode checkout, expiry dates.
- `furniture_store` — home furniture sold from a showroom and delivered.
- `gallery` — art sold on commission for the artists who made it.
- `hardware_shop` — tools and building materials for trade and DIY.
- `thrift_store` — second-hand goods, donated stock, volunteer staffing.
- `toy_store` — toys and games.
- `wine_merchant` — a wine shop, with tastings and events.

## Hospitality

- `bar_industry` — a drinks-led bar or pub with table and self-order service.
- `bowling` — lanes booked by the hour with a bar attached.
- `campsite` — pitches and cabins by the night, with a site shop.
- `catering` — food prepared off site and delivered to events.
- `concert_halls` — ticketed live music, box office and bar.
- `escape_rooms` — timed sessions booked per group.
- `fast_food` — counter and self-order, cooked to order, eaten fast.
- `food_trucks` — mobile service working pitches that move.
- `guest_house` — a handful of rooms let by the night, host-run.
- `guided_tours` — scheduled tours sold by the seat.
- `holiday_house` — a whole property let by the week.
- `hotel` — rooms by the night with a front desk and a restaurant.
- `industry_restaurant` — fine dining: reservations, table service, courses.
- `members_club` — membership on subscription, with events.
- `night_clubs` — a late venue selling tickets and drinks.
- `spa_resort` — treatments booked alongside rooms.
- `student_organization` — a campus body running events and selling to members.
- `takeaway_restaurant` — ordered ahead, collected or delivered, no table service.
- `theater` — ticketed performances sold by season and subscription.

## Services

- `3pl_logistic_company` — warehousing and fulfilment of other people's goods.
- `accounting_firm` — books and accounts kept for client companies, billed on time.
- `architects` — building design billed by project stage.
- `bike_leasing` — bikes on subscription, servicing included.
- `billboard_rental` — advertising space rented by period, with field crews.
- `certification_organism` — audits and inspections ending in a certificate.
- `cleaning_services` — recurring cleaning contracts worked on customer sites.
- `condominium` — a property owners' association charging shared costs.
- `coworking` — desks and meeting rooms on subscription.
- `diy_workshops` — paid hands-on classes, materials sold with them.
- `driving_school` — lessons and tests booked per pupil.
- `dropshipping` — goods sold and shipped by the supplier, no stock held.
- `elearning_platform` — courses sold and watched online.
- `electrician` — electrical work carried out on customer sites.
- `environmental_agency` — environmental assessment and ESG reporting.
- `event_management` — events run end to end for clients.
- `hair_salon` — cuts by appointment, products on the side.
- `handyman` — small on-site repair jobs.
- `headhunter` — recruitment billed per placement.
- `hvac_services` — heating and cooling installed and maintained under contract.
- `industry_lawyer` — a law firm billing by the hour.
- `industry_real_estate` — landlord-side property management: tenants and recurring rent.
- `it_hardware` — IT kit sold with a support desk and repairs behind it.
- `library` — lending on membership, with events.
- `marketing_agency` — campaigns run for clients on retainer.
- `museum` — ticketed collections, memberships and events.
- `non_profit_organization` — donations, members and funded projects.
- `odoo_partner` — Odoo implementation and consulting.
- `photography` — shoots booked and delivered per client.
- `real_estate` — an agency selling property for owners on commission.
- `shoe_maker` — footwear made and repaired to order.
- `software_reseller` — licences resold with the implementation around them.
- `sport_events` — sporting events with booths and exhibitors.
- `summer_camps` — seasonal camps sold per child.
- `surveyor` — land survey and mapping work.
- `tattoo_shop` — artists booked by the session.
- `wedding_planner` — weddings coordinated per client.

## Health and Fitness

- `climbing_gym` — walls on membership, plus courses and events.
- `eyewear_shop` — eye tests and glasses.
- `fitness` — a gym: memberships, classes and kit.
- `mental_therapy` — therapy sessions booked and billed per patient.
- `outdoor_activities` — guided outdoor sessions sold by the place.
- `personal_trainer` — one-to-one sessions billed on time.
- `pet_groomer` — pet grooming by appointment.
- `pharmacy_retail` — dispensing, with expiry dates and margins tracked.
- `physical_therapy` — physiotherapy sessions per patient.
- `sports_club` — a club with courts, members and a bar.
- `team_sports_club` — a team with fixtures, ticketing and a club shop.
- `veterinary_clinic` — animal consultations, visits and treatment.
- `wellness_practitioner` — a single practitioner treating by appointment.
- `yoga_pilates` — a studio selling class passes and memberships.

## Supply Chain

- `beverage_distributor` — drinks wholesaled to trade, with deposits and duty.
- `carpenter` — joinery made to order and fitted.
- `coal_petroleum` — bulk fuel traded, landed costs tracked.
- `corporate_gifts` — branded gifts sourced and personalised for companies.
- `custom_furniture` — furniture manufactured to each order.
- `food_distribution` — food wholesaled, with production planning and expiry.
- `metal_fabricator` — metal cut, welded and fabricated to order.
- `micro_brewery` — beer brewed, poured in the taproom and sold to trade.
- `textile_manufacturing` — fabric and garments produced, partly subcontracted.
- `vineyard` — grapes grown, wine made and sold at the cellar door.

## Construction

- `construction` — building work run as projects on site.
- `construction_developer` — develops and sells the projects it builds.
- `gardening` — landscaping and grounds maintenance on customer sites.
- `machine_tool_rental` — plant and tools hired out by period.
- `solar_installation` — solar surveyed, installed and serviced.

## Arriving as dependencies

These are the shared parts the trades above are built from. They come in on
their own when a trade needs them, so the pick stays with the trade:
`base_industry_data`, `booking_engine`, `account_pos_settle_due`,
`deposit_management`, `excise_management`, `product_conversion`,
`recurring_rental_billing`, `usage_based_maintenance`.
