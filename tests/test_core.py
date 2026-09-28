import json
import unittest

from spacegarden import core
from spacegarden.core import SpaceGarden


def _fill_slots(garden, count=core.SLOT_COUNT):
    for _ in range(count):
        garden.apply(core.CMD_SOW)


class NutrientConsumptionTest(unittest.TestCase):
    def test_consumed_once_per_tick(self):
        garden = SpaceGarden(seed=1)
        _fill_slots(garden, 2)
        nutrient_before = garden.nutrient
        self.assertEqual(garden.apply(core.CMD_END_TICK), core.MSG_OK)
        self.assertEqual(nutrient_before - garden.nutrient,
                         2 * core.NUTRIENT_PER_PLANT)
        self.assertEqual(garden.apply(core.CMD_END_TICK), core.MSG_OK)
        self.assertEqual(nutrient_before - garden.nutrient,
                         4 * core.NUTRIENT_PER_PLANT)

    def test_single_tick_does_not_consume_twice(self):
        garden = SpaceGarden(seed=1)
        _fill_slots(garden, 3)
        nutrient_before = garden.nutrient
        garden.apply(core.CMD_END_TICK)
        self.assertNotEqual(nutrient_before - garden.nutrient,
                            2 * 3 * core.NUTRIENT_PER_PLANT)

    def test_no_consumption_without_plants(self):
        garden = SpaceGarden(seed=1)
        nutrient_before = garden.nutrient
        garden.apply(core.CMD_END_TICK)
        self.assertEqual(garden.nutrient, nutrient_before)


class LightGrowthTest(unittest.TestCase):
    def test_growth_with_lights_on(self):
        garden = SpaceGarden(seed=1)
        garden.apply(core.CMD_SOW)
        garden.apply(core.CMD_END_TICK)
        plant = next(p for p in garden.plants if p is not None)
        self.assertEqual(plant["age"], 1)
        self.assertEqual(plant["maturity"], core.MATURITY_PER_AGE)

    def test_no_growth_with_lights_off(self):
        garden = SpaceGarden(seed=1)
        garden.apply(core.CMD_SOW)
        garden.apply(core.CMD_LIGHT_OFF)
        garden.apply(core.CMD_END_TICK)
        plant = next(p for p in garden.plants if p is not None)
        self.assertEqual(plant["age"], 0)
        self.assertEqual(plant["maturity"], 0)

    def test_lights_off_still_costs_resources(self):
        garden = SpaceGarden(seed=1)
        garden.apply(core.CMD_SOW)
        garden.apply(core.CMD_LIGHT_OFF)
        nutrient_before = garden.nutrient
        garden.apply(core.CMD_END_TICK)
        self.assertEqual(nutrient_before - garden.nutrient,
                         core.NUTRIENT_PER_PLANT)


class SickRemovalTest(unittest.TestCase):
    def test_remove_sick_frees_slot(self):
        garden = SpaceGarden(seed=1)
        _fill_slots(garden)
        garden.plants[1]["sick"] = True
        self.assertEqual(garden.plant_count(), core.SLOT_COUNT)
        self.assertEqual(garden.apply(core.CMD_REMOVE_SICK), core.MSG_OK)
        self.assertIsNone(garden.plants[1])
        self.assertEqual(garden.plant_count(), core.SLOT_COUNT - 1)
        self.assertEqual(garden.apply(core.CMD_SOW), core.MSG_OK)
        self.assertEqual(garden.plant_count(), core.SLOT_COUNT)

    def test_remove_without_sick_rejected(self):
        garden = SpaceGarden(seed=1)
        _fill_slots(garden, 2)
        self.assertEqual(garden.apply(core.CMD_REMOVE_SICK), core.MSG_NO_SICK)
        self.assertEqual(garden.plant_count(), 2)


class HarvestTest(unittest.TestCase):
    def test_harvest_uses_current_maturity(self):
        garden = SpaceGarden(seed=1)
        garden.apply(core.CMD_SOW)
        plant = next(p for p in garden.plants if p is not None)
        plant["age"] = 5
        plant["maturity"] = 0  # 故意写入过期缓存
        self.assertEqual(garden.apply(core.CMD_HARVEST), core.MSG_OK)
        self.assertEqual(garden.plant_count(), 0)
        self.assertEqual(garden.energy, 50 + core.HARVEST_ENERGY)

    def test_stale_high_maturity_does_not_count(self):
        garden = SpaceGarden(seed=1)
        garden.apply(core.CMD_SOW)
        plant = next(p for p in garden.plants if p is not None)
        plant["age"] = 1
        plant["maturity"] = core.MATURITY_MAX  # 旧成熟度
        self.assertEqual(garden.apply(core.CMD_HARVEST),
                         core.MSG_NOT_MATURE)
        self.assertEqual(garden.plant_count(), 1)

    def test_immature_not_harvestable(self):
        garden = SpaceGarden(seed=1)
        garden.apply(core.CMD_SOW)
        self.assertEqual(garden.apply(core.CMD_HARVEST),
                         core.MSG_NOT_MATURE)


class WaterTankTest(unittest.TestCase):
    def test_full_tank_rejects_water(self):
        garden = SpaceGarden(seed=1)
        garden.water = core.MAX_WATER
        self.assertEqual(garden.apply(core.CMD_WATER), core.MSG_WATER_FULL)
        self.assertEqual(garden.water, core.MAX_WATER)

    def test_water_capped_at_max(self):
        garden = SpaceGarden(seed=1)
        garden.water = core.MAX_WATER - 5
        self.assertEqual(garden.apply(core.CMD_WATER), core.MSG_OK)
        self.assertEqual(garden.water, core.MAX_WATER)

    def test_nutrient_capped_at_max(self):
        garden = SpaceGarden(seed=1)
        garden.nutrient = core.MAX_NUTRIENT - 2
        self.assertEqual(garden.apply(core.CMD_NUTRIENT), core.MSG_OK)
        self.assertEqual(garden.nutrient, core.MAX_NUTRIENT)
        self.assertEqual(garden.apply(core.CMD_NUTRIENT),
                         core.MSG_NUTRIENT_FULL)


class AirlockTest(unittest.TestCase):
    def test_fault_blocks_repot(self):
        garden = SpaceGarden(seed=1)
        garden.apply(core.CMD_SOW)
        plant = next(p for p in garden.plants if p is not None)
        garden.airlock_ok = False
        age_before = plant["age"]
        self.assertEqual(garden.apply(core.CMD_REPOT),
                         core.MSG_AIRLOCK_FAULT)
        self.assertEqual(plant["age"], age_before)

    def test_fault_blocks_sow(self):
        garden = SpaceGarden(seed=1)
        garden.airlock_ok = False
        self.assertEqual(garden.apply(core.CMD_SOW),
                         core.MSG_AIRLOCK_FAULT)
        self.assertEqual(garden.plant_count(), 0)

    def test_fix_airlock_restores_operation(self):
        garden = SpaceGarden(seed=1)
        garden.apply(core.CMD_SOW)
        garden.airlock_ok = False
        self.assertEqual(garden.apply(core.CMD_REPOT),
                         core.MSG_AIRLOCK_FAULT)
        self.assertEqual(garden.apply(core.CMD_FIX_AIRLOCK), core.MSG_OK)
        self.assertEqual(garden.apply(core.CMD_REPOT), core.MSG_OK)


class UndoRepotTest(unittest.TestCase):
    def test_undo_restores_plant_age(self):
        garden = SpaceGarden(seed=1)
        garden.apply(core.CMD_SOW)
        plant = next(p for p in garden.plants if p is not None)
        plant["age"] = 3
        self.assertEqual(garden.apply(core.CMD_REPOT), core.MSG_OK)
        self.assertEqual(plant["age"], 3 + core.REPOT_BOOST)
        self.assertEqual(garden.apply(core.CMD_UNDO_REPOT), core.MSG_OK)
        self.assertEqual(plant["age"], 3)

    def test_undo_without_repot_rejected(self):
        garden = SpaceGarden(seed=1)
        garden.apply(core.CMD_SOW)
        self.assertEqual(garden.apply(core.CMD_UNDO_REPOT),
                         core.MSG_NOTHING_TO_UNDO)

    def test_undo_only_once(self):
        garden = SpaceGarden(seed=1)
        garden.apply(core.CMD_SOW)
        garden.apply(core.CMD_REPOT)
        garden.apply(core.CMD_UNDO_REPOT)
        self.assertEqual(garden.apply(core.CMD_UNDO_REPOT),
                         core.MSG_NOTHING_TO_UNDO)


class HumidityReplayTest(unittest.TestCase):
    def test_same_seed_same_sequence(self):
        garden_a = SpaceGarden(seed=9)
        garden_b = SpaceGarden(seed=9)
        for _ in range(5):
            garden_a.apply(core.CMD_END_TICK)
            garden_b.apply(core.CMD_END_TICK)
        self.assertEqual(garden_a.save(), garden_b.save())

    def test_no_duplicate_humidity_after_load(self):
        garden = SpaceGarden(seed=9)
        _fill_slots(garden, 2)
        for _ in range(3):
            garden.apply(core.CMD_END_TICK)
        restored = SpaceGarden.load(garden.save())
        self.assertEqual(restored.log, garden.log)
        for _ in range(2):
            garden.apply(core.CMD_END_TICK)
            restored.apply(core.CMD_END_TICK)
        self.assertEqual(restored.save(), garden.save())

    def test_preview_does_not_change_random_order(self):
        garden = SpaceGarden(seed=9)
        first = [garden.humidity_gain(tick) for tick in range(1, 9)]
        garden.preview_events(3)
        garden.humidity_gain(3)
        second = [garden.humidity_gain(tick) for tick in range(1, 9)]
        self.assertEqual(first, second)


class IllegalCommandTest(unittest.TestCase):
    def test_unknown_command_rejected(self):
        garden = SpaceGarden(seed=1)
        snapshot = garden.save()
        self.assertEqual(garden.apply("打开舱门"), core.MSG_INVALID)
        self.assertEqual(garden.save(), snapshot)

    def test_empty_command_rejected(self):
        garden = SpaceGarden(seed=1)
        self.assertEqual(garden.apply(""), core.MSG_INVALID)


class EmptyDataTest(unittest.TestCase):
    def test_load_empty_save_rejected(self):
        with self.assertRaises(ValueError):
            SpaceGarden.load({})

    def test_load_missing_keys_rejected(self):
        with self.assertRaises(ValueError):
            SpaceGarden.load({"tick": 1, "water": 50})

    def test_save_load_roundtrip(self):
        garden = SpaceGarden(seed=3)
        garden.apply(core.CMD_SOW)
        garden.apply(core.CMD_END_TICK)
        restored = SpaceGarden.load(json.loads(json.dumps(garden.save())))
        self.assertEqual(restored.save(), garden.save())
        self.assertEqual(set(garden.save()), set(core.SAVE_KEYS))


class CapacityBoundaryTest(unittest.TestCase):
    def test_water_cannot_exceed_max(self):
        garden = SpaceGarden(seed=1)
        garden.water = core.MAX_WATER - 1
        garden.apply(core.CMD_WATER)
        self.assertEqual(garden.apply(core.CMD_WATER), core.MSG_WATER_FULL)
        self.assertEqual(garden.water, core.MAX_WATER)

    def test_energy_capped_at_max(self):
        garden = SpaceGarden(seed=1)
        garden.apply(core.CMD_SOW)
        plant = next(p for p in garden.plants if p is not None)
        plant["age"] = 5
        garden.energy = core.MAX_ENERGY
        self.assertEqual(garden.apply(core.CMD_HARVEST), core.MSG_OK)
        self.assertEqual(garden.energy, core.MAX_ENERGY)

    def test_slots_cannot_overflow(self):
        garden = SpaceGarden(seed=1)
        _fill_slots(garden)
        self.assertEqual(garden.apply(core.CMD_SOW), core.MSG_NO_SLOT)
        self.assertEqual(garden.plant_count(), core.SLOT_COUNT)


class DuplicateInputTest(unittest.TestCase):
    def test_duplicate_sows_and_water(self):
        garden = SpaceGarden(seed=1)
        sow_results = [garden.apply(core.CMD_SOW)
                       for _ in range(core.SLOT_COUNT + 1)]
        self.assertEqual(sow_results[:-1],
                         [core.MSG_OK] * core.SLOT_COUNT)
        self.assertEqual(sow_results[-1], core.MSG_NO_SLOT)
        water_results = [garden.apply(core.CMD_WATER) for _ in range(4)]
        self.assertIn(core.MSG_WATER_FULL, water_results)
        self.assertEqual(garden.water, core.MAX_WATER)

    def test_duplicate_remove_sick(self):
        garden = SpaceGarden(seed=1)
        _fill_slots(garden, 2)
        garden.plants[0]["sick"] = True
        self.assertEqual(garden.apply(core.CMD_REMOVE_SICK), core.MSG_OK)
        self.assertEqual(garden.apply(core.CMD_REMOVE_SICK),
                         core.MSG_NO_SICK)
        self.assertEqual(garden.plant_count(), 1)


class DemoTest(unittest.TestCase):
    def test_fixed_demo_runs(self):
        garden = core.run_demo()
        self.assertIsInstance(garden, SpaceGarden)
        self.assertGreater(garden.tick, 1)

    def test_demo_is_deterministic(self):
        first = core.run_demo().save()
        second = core.run_demo().save()
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
