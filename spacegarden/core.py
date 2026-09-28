"""空间温室回合制后端。

每回合（tick）原子结算：资源消耗、生长与随机事件一次性应用；
事件随机流按 (seed, tick) 派生，重放或恢复存档不会改变随机顺序，
也不会让同一 tick 的事件重复生效。
"""
from __future__ import annotations

import random

SAVE_KEYS = (
    "tick", "water", "nutrient", "energy", "lights_on",
    "airlock_ok", "slots", "plants", "seed", "log",
)

MAX_WATER = 100
WATER_PER_ADD = 20
WATER_PER_PLANT = 2
MAX_NUTRIENT = 50
NUTRIENT_PER_ADD = 10
NUTRIENT_PER_PLANT = 1
MAX_ENERGY = 100
SLOT_COUNT = 4
MATURITY_PER_AGE = 20
MATURITY_MAX = 100
HARVEST_MIN = 100
HARVEST_ENERGY = 10
REPOT_BOOST = 2
HUMIDITY_WATER = 8

MSG_OK = "命令已执行"
MSG_INVALID = "未知命令"
MSG_WATER_FULL = "水箱已满"
MSG_NUTRIENT_FULL = "营养液已满"
MSG_NO_SLOT = "没有空位"
MSG_NO_PLANT = "没有植物"
MSG_NOT_MATURE = "尚未成熟"
MSG_NO_SICK = "没有病株"
MSG_AIRLOCK_FAULT = "气闸故障，操作被阻止"
MSG_NOTHING_TO_UNDO = "没有可撤销的换盆"
MSG_HUMIDITY = "湿度事件：冷凝水回收"
MSG_AIRLOCK_BROKEN = "气闸故障警报"
MSG_SICK = "病害爆发"

CMD_WATER = "加水"
CMD_NUTRIENT = "添加营养液"
CMD_LIGHT_ON = "开灯"
CMD_LIGHT_OFF = "关灯"
CMD_SOW = "播种"
CMD_HARVEST = "收获"
CMD_REMOVE_SICK = "移除病株"
CMD_REPOT = "换盆"
CMD_UNDO_REPOT = "撤销换盆"
CMD_FIX_AIRLOCK = "修理气闸"
CMD_END_TICK = "结束回合"


class SpaceGarden:
    def __init__(self, seed=7):
        self.tick = 1
        self.water = 60
        self.nutrient = 30
        self.energy = 50
        self.lights_on = True
        self.airlock_ok = True
        self.slots = SLOT_COUNT
        self.plants = [None] * SLOT_COUNT
        self.seed = seed
        self.log = []
        self._last_repot = None

    @staticmethod
    def maturity_of(plant):
        """成熟度始终由当前年龄现算，不使用缓存的旧值。"""
        return min(plant["age"] * MATURITY_PER_AGE, MATURITY_MAX)

    def plant_count(self):
        return sum(1 for plant in self.plants if plant is not None)

    def _free_slot(self):
        for index, plant in enumerate(self.plants):
            if plant is None:
                return index
        return None

    def _event_rng(self, tick, tag):
        return random.Random("%s:%s:%s" % (self.seed, tick, tag))

    def humidity_gain(self, tick):
        """湿度事件回收的水量：由 (seed, tick) 决定，重放不重复。"""
        if self._event_rng(tick, "humidity").randint(1, 4) == 1:
            return HUMIDITY_WATER
        return 0

    def airlock_breaks(self, tick):
        return self._event_rng(tick, "airlock").randint(1, 6) == 1

    def sick_strikes(self, tick):
        return self._event_rng(tick, "sick").randint(1, 5) == 1

    def preview_events(self, tick):
        messages = []
        if self.humidity_gain(tick):
            messages.append(MSG_HUMIDITY)
        if self.airlock_breaks(tick):
            messages.append(MSG_AIRLOCK_BROKEN)
        if self.sick_strikes(tick) and self.plant_count() > 0:
            messages.append(MSG_SICK)
        return messages

    def apply(self, command):
        if command == CMD_WATER:
            return self._add_water()
        if command == CMD_NUTRIENT:
            return self._add_nutrient()
        if command == CMD_LIGHT_ON:
            self.lights_on = True
            return MSG_OK
        if command == CMD_LIGHT_OFF:
            self.lights_on = False
            return MSG_OK
        if command == CMD_SOW:
            return self._sow()
        if command == CMD_HARVEST:
            return self._harvest()
        if command == CMD_REMOVE_SICK:
            return self._remove_sick()
        if command == CMD_REPOT:
            return self._repot()
        if command == CMD_UNDO_REPOT:
            return self._undo_repot()
        if command == CMD_FIX_AIRLOCK:
            self.airlock_ok = True
            return MSG_OK
        if command == CMD_END_TICK:
            return self._end_tick()
        return MSG_INVALID

    def _add_water(self):
        if self.water >= MAX_WATER:
            return MSG_WATER_FULL
        self.water = min(MAX_WATER, self.water + WATER_PER_ADD)
        return MSG_OK

    def _add_nutrient(self):
        if self.nutrient >= MAX_NUTRIENT:
            return MSG_NUTRIENT_FULL
        self.nutrient = min(MAX_NUTRIENT, self.nutrient + NUTRIENT_PER_ADD)
        return MSG_OK

    def _sow(self):
        if not self.airlock_ok:
            return MSG_AIRLOCK_FAULT
        slot = self._free_slot()
        if slot is None:
            return MSG_NO_SLOT
        self.plants[slot] = {"age": 0, "maturity": 0, "sick": False}
        return MSG_OK

    def _harvest(self):
        for index, plant in enumerate(self.plants):
            if plant is None:
                continue
            maturity = self.maturity_of(plant)
            if maturity >= HARVEST_MIN:
                self.plants[index] = None
                self.energy = min(MAX_ENERGY, self.energy + maturity // 10)
                return MSG_OK
        return MSG_NOT_MATURE

    def _remove_sick(self):
        for index, plant in enumerate(self.plants):
            if plant is not None and plant["sick"]:
                self.plants[index] = None
                return MSG_OK
        return MSG_NO_SICK

    def _repot(self):
        if not self.airlock_ok:
            return MSG_AIRLOCK_FAULT
        for index, plant in enumerate(self.plants):
            if plant is not None:
                self._last_repot = (index, plant["age"])
                plant["age"] += REPOT_BOOST
                plant["maturity"] = self.maturity_of(plant)
                return MSG_OK
        return MSG_NO_PLANT

    def _undo_repot(self):
        if self._last_repot is None:
            return MSG_NOTHING_TO_UNDO
        index, previous_age = self._last_repot
        plant = self.plants[index]
        if plant is None:
            self._last_repot = None
            return MSG_NOTHING_TO_UNDO
        plant["age"] = previous_age
        plant["maturity"] = self.maturity_of(plant)
        self._last_repot = None
        return MSG_OK

    def _end_tick(self):
        # 原子结算：事件、消耗、生长按当前 tick 一次性应用。
        events = self.preview_events(self.tick)

        humidity = self.humidity_gain(self.tick)
        if humidity:
            self.water = min(MAX_WATER, self.water + humidity)

        count = self.plant_count()
        water_cost = count * WATER_PER_PLANT
        nutrient_cost = count * NUTRIENT_PER_PLANT
        if self.water >= water_cost and self.nutrient >= nutrient_cost:
            # 营养液与水每 tick 只消耗一次。
            self.water -= water_cost
            self.nutrient -= nutrient_cost
            if self.lights_on:
                for plant in self.plants:
                    if plant is not None and not plant["sick"]:
                        plant["age"] += 1
                        plant["maturity"] = self.maturity_of(plant)

        if self.airlock_breaks(self.tick):
            self.airlock_ok = False

        if self.sick_strikes(self.tick):
            for plant in self.plants:
                if plant is not None and not plant["sick"]:
                    plant["sick"] = True
                    break

        self.log.extend(events)
        self.tick += 1
        return MSG_OK

    def save(self):
        return {key: getattr(self, key) for key in SAVE_KEYS}

    @classmethod
    def load(cls, data):
        if not data:
            raise ValueError("存档数据为空")
        missing = [key for key in SAVE_KEYS if key not in data]
        if missing:
            raise ValueError("存档缺少键: %s" % ",".join(missing))
        garden = cls(seed=data["seed"])
        for key in SAVE_KEYS:
            setattr(garden, key, data[key])
        garden.plants = [
            dict(plant) if plant is not None else None
            for plant in data["plants"]
        ]
        garden.log = list(data["log"])
        return garden


def run_demo():
    """固定种子演示：脚本化命令序列，输出确定。"""
    garden = SpaceGarden(seed=42)
    script = [
        CMD_SOW, CMD_SOW, CMD_WATER, CMD_NUTRIENT, CMD_END_TICK,
        CMD_LIGHT_OFF, CMD_END_TICK,
        CMD_LIGHT_ON, CMD_END_TICK,
        CMD_REPOT, CMD_UNDO_REPOT, CMD_END_TICK,
        CMD_END_TICK,
        CMD_HARVEST, CMD_REMOVE_SICK, CMD_FIX_AIRLOCK,
    ]
    for command in script:
        print("第%d回合 [%s] -> %s" % (garden.tick, command, garden.apply(command)))
    state = garden.save()
    print("存档:", {key: state[key] for key in SAVE_KEYS})
    return garden


if __name__ == "__main__":
    run_demo()
