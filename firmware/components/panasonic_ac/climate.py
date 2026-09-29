import esphome.codegen as cg
from esphome.components import climate_ir

AUTO_LOAD = ["climate_ir"]

panasonic_ac_ns = cg.esphome_ns.namespace("panasonic_ac")
PanasonicClimate = panasonic_ac_ns.class_("PanasonicClimate", climate_ir.ClimateIR)

CONFIG_SCHEMA = climate_ir.climate_ir_with_receiver_schema(PanasonicClimate)


async def to_code(config):
    await climate_ir.new_climate_ir(config)
