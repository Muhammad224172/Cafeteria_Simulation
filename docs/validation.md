# Validation against the Arena models

There are two Arena models to compare against. Neither is expected to agree exactly, because each
encodes its own reading of the problem. The aim is to show that when this model adopts the same
readings, it reproduces the reference numbers, and that the remaining gaps have identifiable
causes. The reference values and their source files are listed in
`validation/arena_reference.yaml`. The comparison table is generated into `results/validation.md`
by `scripts/validate.py`, and the figure is `results/figures/validation.png`.

## 1. The instructor's solution model

This is the model handed out for Part 3, credited in the file to Sinan Yildirim. The group ran it
for 20 replications for Part 3(a) (run of 2024-01-16). Its replication stops when it is past
20:00 and the cafeteria is empty, so its measure 2 is averaged until the last diner leaves. Below,
this model's measure 2 uses the same window.

| | Measure 1 (s) | Measure 2 | Day ends (min after 11:30) |
|---|---|---|---|
| Arena, instructor model, 20 reps | 54.3 ± 2.4 | 324.0 ± 7.9 | 577.4 |
| This model, problem reading (`base`) | 47.6 ± 1.3 | 455.0 ± 19.9 | 622.1 |
| This model, instructor reading (`s02`) | 51.2 ± 1.3 | 316.2 ± 10.4 | 575.1 |

95% t-intervals over 20 replications. A Welch test of `s02` against Arena gives p = 0.22 for
measure 2 and p = 0.026 for measure 1.

### Where the base gap comes from

Starting from `base`, I switched on the instructor model's readings one at a time. All runs use 20
replications on the same random numbers.

| Change | Measure 1 (s) | Measure 2, until empty | Day ends (min) | Mean table wait (min) |
|---|---|---|---|---|
| base | 47.6 | 455.0 | 622 | 59.3 |
| + dining time of the first member to finish | 47.6 | 315.7 | 574 | 32.3 |
| + one line choice per group | 51.2 | 455.4 | 622 | 59.4 |
| + both (= `s02`) | 51.2 | 316.2 | 575 | 32.5 |

- **Measure 2 is almost entirely the dining-time reading.** The dining hall is saturated: 144
  seats, while roughly 900 customers an hour arrive in the 11:30-12:00 peak. So every minute of
  table occupancy turns into queueing for tables.
  - The instructor file's `15*BETA(1, group size) + 15` gives a group the dining time of its
    *fastest* eater (decision 17 in `modelling_decisions.md`). That shortens table occupancy for
    every party of two or more.
  - With that one change, this model gives 315.7 against Arena's 324.0, and a closing time of
    574 min against 577.
  - The problem text, and the assignment's own Part 1(b) answer, describe the *slowest* eater.
    So the base keeps that reading.
- **Measure 1 is shifted mainly by line choice.** When a whole group goes to one line (Instructor)
  rather than each person choosing (problem reading), its members reach every station
  back-to-back. Cashier waiting rises from 7.5 to 9.0 s, and measure 1 rises by 3.6 s.

### What is left after matching the readings

Measure 2 agrees: 316 ± 10 against 324 ± 8, p = 0.22. Measure 1 is still about 3 s lower than
Arena (51.2 ± 1.3 against 54.3 ± 2.4, p = 0.026). Candidate causes, none of which I can verify
from the binary files:

- In the solution file as it is on disk, the experience slowdown evaluates to 1.4 for both
  worker pools (decision 15).
  - Applying 1.4 to *every* task time overshoots badly, to about 74 s, so the run being compared
    against probably did not have it.
  - But a partial version of it would increase stockouts and could account for a few seconds.
- The instructor model gives Task 1 and Task 2 the same priority. It also picks workers at random
  between the two pools.
- The instructor model signals "shelf not full" only after a customer finishes taking the item,
  2 to 5 s later. This model makes the top-up pending at once, so its shelves are refilled sooner.
- Arena's handling of the table queue, and the "Wait" schedule rule, may differ in small details.

The model reproduces the Arena run's closing time to within about 2 minutes. It also places about
10,800 shelf items a day, against 10,674 in the one Arena replication whose report lists them.
That run is a modified copy of the model, so this is a rough check.

## 2. The group's Part 2 model

This is the group's final Arena model, of 2024-01-08: one replication of a fixed 8.5 hours.
- It is a partial implementation of the system. The compiled model has no worker, shelf or
  table-capacity logic.
- Its arrival schedule is entered at a third of the table, as 200/150/60/50/150/80 arrival events
  per hour.
- The main-dish branch probability is entered as 0.95/100 rather than 95/100.

Its numbers therefore validate only the arrival and eating structure. To make the inputs
comparable, I ran this model with the same arrival schedule (scenario `s05`).

| | Customers | Time-average number in system, 11:30-20:00 | Mean time in system (s) |
|---|---|---|---|
| Arena, group Part 2 model (1 rep) | 1,251 | 57.1 | 1,437 |
| This model, `s05` (20 reps) | 1,112 | 54.0 ± 1.1 | 1,522 |

At this lower load the dining hall is not a constraint, and the time-average number in the
cafeteria matches to within about 5%. The single Arena replication has more customers than this
model's 20-day mean (1,251 against 1,112). It is one draw, and that model's arrival module also
assigns group sizes differently, so I do not read more into it.

The mean time in system is about 85 s higher here. This is consistent with this model giving a
group the dining time of its slowest member, while the group's model delays each person
independently.

## 3. Instructor model runs that are not used

The course folder also holds two later 20-replication runs, of 2024-01-18 (measure 1 of 48.2 s
and 47.6 s, measure 2 of about 326). They were made with a modified copy of the solution model,
with two-unit cashiers, a 20-unit sauce table and a different worker schedule. These appear to be
the group's Part 3 alternative, so they are not used as a validation target.

Under this repository's cost accounting, that worker schedule would cost more than the base
schedule, before counting any extra cashiers. The direction of its result does agree with the
alternative selected here: more till capacity cuts measure 1 by roughly 6 s and leaves measure 2
unchanged.
