# The system being modelled

This is a restatement, in my own words, of the system studied in the IE 305 (Simulation) term
project at Sabancı University, Fall 2023-24. Every number used by the model is in
`configs/base.yaml`; the table at the end lists them with their meaning.

## Setting

A university cafeteria serves lunch and dinner without a break from 11:30 to 20:00. Customers
come alone or in small groups. Each customer picks food along one of four parallel serving lines,
pays at the end of the line, may stop at a shared sauce-and-spice table, and then eats in a dining
hall. Workers behind the lines keep the food shelves stocked. Management wants to estimate two
quantities for a typical day, and then find a staffing or line policy that does better without
costing more:

1. **Measure 1**: the expected average time from a customer's arrival to the end of their payment.
2. **Measure 2**: the expected time-average number of customers inside the cafeteria, counting both
   the serving lines and the dining hall.

## Arrivals

Arrivals follow a non-stationary Poisson process whose rate is constant within each of six
periods (table below). An arrival brings `min(1 + N, 6)` people, where `N` is Poisson with mean
0.5; most arrivals are a single person (P = 0.61). No one arrives after 20:00.

## Serving lines

Lines A, B, C and D stand side by side. Each customer has a meal preference:

| Preference | Share | Line |
|---|---|---|
| Vegan main dish | 10% | A |
| Standard main dish | 60% | B or D, whichever currently has fewer customers |
| Salad as the main dish | 30% | C |

Every line has the same sequence of stations: tray, dessert, main dish, side dish, soup and bread,
cutlery, payment. Moving from one station to the next takes 1 to 2 seconds. At each food station a
customer either takes one item (with the probability in the table) or walks past. If the item
they want is not on the shelf, they wait at the station until a worker puts one there. Everyone
takes cutlery.

At the till, a customer pays by credit card (10%), cash (10%) or university card (80%). A
university card usually has enough credit (95%). Otherwise it has to be topped up first, which
makes the payment much longer.

After paying, 60% of customers walk to the sauce-and-spice table, which has room for 10 people
at once. Members of a group may be split across lines, so the group re-forms after payment
(and after the sauce table) and then looks for a table together.

## Dining hall

There are 24 tables with 6 seats each. A party takes an empty table if there is one. Otherwise it
takes the least occupied table that still has enough free seats for the whole party. If no table
can seat the party, it waits. Each person eats for a uniform 15 to 30 minutes, and the party
leaves when its slowest member is done. Trays and dishes are assumed always available, so
returning them is not modelled.

The cafeteria closes once it is past 20:00 and the serving lines are empty.

## Staff

Every line has one cashier at all times. Behind the lines there are two working areas, one
shared by lines A and B and one shared by lines C and D. The workers in an area serve both of its
lines and do three kinds of task, in strict priority order:

1. **Replace an empty food container.** Each line has one container per food type, holding 40
   desserts, 45 main dishes, 45 side dishes or 50 soups. Replacing one takes an exponential time
   with mean 40 s.
2. **Refill an empty cutlery container.** Each line holds 100 sets. Refilling takes an exponential
   time with mean 40 s.
3. **Top up a shelf.** Each line's shelf holds up to 10 desserts, 5 main dishes, 5 side dishes and
   5 soups. Putting one ready item (dessert, or a salad bowl on line C) on the shelf takes 1 to 2 s.
   Plating a main dish, side dish or soup from the container and putting it on the shelf takes
   longer. The assignment gave a data file of measured plating times for this.

The first available worker takes the most urgent pending task. Workers are either experienced or
inexperienced. The task times above are for experienced workers, and inexperienced workers take
40% longer on average. The number of each kind on duty changes by the hour (schedule below).

## Costs

An experienced worker earns 1.3 times the hourly wage of an inexperienced worker, and cashiers are
paid like experienced workers. Nobody is paid for time after 20:00. The model measures cost in
units of one inexperienced worker-hour.

## Parameters

Times are in seconds unless noted. UNIF(a, b) is uniform, TRIA(a, m, b) is triangular,
EXPO(m) is exponential with mean m, and NORM(m, s) is normal.

| Group | Parameter | Value |
|---|---|---|
| Arrivals | arrivals per hour, 11:30-12:00 | 600 |
| | 12:00-13:00 | 450 |
| | 13:00-14:00 | 180 |
| | 14:00-18:00 | 150 |
| | 18:00-19:00 | 450 |
| | 19:00-20:00 | 240 |
| | group size | min(1 + POIS(0.5), 6) |
| Routing | vegan / standard / salad | 0.10 / 0.60 / 0.30 |
| Stations | walk between stations | UNIF(1, 2) |
| | tray | UNIF(1, 2) |
| | dessert: P(take), time | 0.60, UNIF(2, 5) |
| | main dish | 0.95, UNIF(2, 5) |
| | side dish | 0.75, UNIF(2, 5) |
| | soup and bread | 0.90, UNIF(2, 5) |
| | cutlery | UNIF(3, 6) |
| Payment | credit card (P = 0.10) | TRIA(1, 4, 7) |
| | cash (P = 0.10) | TRIA(10, 15, 20) |
| | university card, enough credit (P = 0.80 x 0.95) | TRIA(1, 4, 7) |
| | university card, top-up needed (P = 0.80 x 0.05) | TRIA(40, 70, 100) |
| Sauce table | P(visit), walk, use time, capacity | 0.60, UNIF(5, 15), TRIA(5, 15, 30), 10 |
| Dining | tables x seats | 24 x 6 |
| | eating time per person | UNIF(15, 30) min |
| Supplies | shelf capacity: dessert / main / side / soup | 10 / 5 / 5 / 5 |
| | container units: dessert / main / side / soup | 40 / 45 / 45 / 50 |
| | cutlery sets per line | 100 |
| Tasks | Task 1, replace container | EXPO(40) |
| | Task 2, refill cutlery | EXPO(40) |
| | Task 3, ready item (dessert, salad) | UNIF(1, 2) |
| | Task 3, plated item (main, side, soup) | NORM(8, 2), see `modelling_decisions.md` |
| | inexperienced slowdown | x 1.4 |
| Staff | per area (AB and CD), experienced + inexperienced, 11:30-14:00 | 3 + 3 |
| | 14:00-18:00 | 2 + 2 |
| | 18:00-20:00 and after | 3 + 3 |
| | cashiers | 1 per line |
| Costs | inexperienced / experienced / cashier, per hour | 1.0 / 1.3 / 1.3 |
| | paid until | 20:00 |
