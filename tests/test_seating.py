import pytest
import simpy

from cafesim.seating import DiningArea, choose_table


def test_empty_table_preferred_lowest_index():
    assert choose_table([3, 0, 0, 5], 6, 1) == 1
    assert choose_table([3, 0, 0, 5], 6, 6) == 1


def test_least_occupied_table_that_fits():
    # no empty table: a single takes the least occupied table
    assert choose_table([4, 2, 5, 3], 6, 1) == 1
    # a party of 3 needs >= 3 free seats: tables 1 (2 used) and 3 (3 used); least occupied wins
    assert choose_table([4, 2, 5, 3], 6, 3) == 1
    # a party of 4 fits only at table 1
    assert choose_table([4, 2, 5, 3], 6, 4) == 1
    # ties go to the lowest index
    assert choose_table([2, 2, 5], 6, 2) == 0


def test_no_table_fits():
    assert choose_table([4, 3, 5], 6, 4) is None
    assert choose_table([6, 6], 6, 1) is None


def test_party_larger_than_table_rejected():
    with pytest.raises(ValueError):
        choose_table([0], 6, 7)


def _run_queue(allow_overtaking):
    env = simpy.Environment()
    dining = DiningArea(env, tables=1, seats=6, allow_overtaking=allow_overtaking)
    seated_at = {}

    def party(name, size, arrive, stay):
        yield env.timeout(arrive)
        table = yield dining.request(size)
        seated_at[name] = env.now
        yield env.timeout(stay)
        dining.release(table, size)

    env.process(party("first", 4, 0, 10))  # occupies 4 of 6 seats until t=10
    env.process(party("big", 4, 1, 5))  # needs 4 seats: must wait
    env.process(party("small", 1, 2, 5))  # one seat is free now
    env.run()
    return seated_at


def test_fifo_queue_blocks_behind_large_party():
    seated = _run_queue(allow_overtaking=False)
    assert seated["first"] == 0
    assert seated["big"] == 10
    assert seated["small"] == 10  # waits behind "big", then both fit (4 + 1 <= 6)


def test_overtaking_lets_small_party_through():
    seated = _run_queue(allow_overtaking=True)
    assert seated["small"] == 2
    assert seated["big"] == 10
