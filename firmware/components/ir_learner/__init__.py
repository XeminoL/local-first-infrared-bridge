import esphome.codegen as cg
import esphome.config_validation as cv
from esphome import automation, pins
from esphome.components import remote_base
from esphome.const import CONF_ID, CONF_PIN, CONF_TRIGGER_ID

CONF_TRANSMITTER = "transmitter_id"
CONF_SLOTS = "slots"
CONF_MAX_TIMINGS = "max_timings"
CONF_END_SILENCE = "end_silence"
CONF_LEARN_TIMEOUT = "learn_timeout"
CONF_SHORTEST_PULSE = "shortest_pulse"
CONF_CARRIER = "carrier_frequency"
CONF_ECHO_TOLERANCE = "echo_tolerance"
CONF_ECHO_SLACK = "echo_slack"
CONF_ON_STATUS = "on_status"
CONF_ON_LEARNED = "on_learned"
CONF_ON_ECHO = "on_echo"

ir_learner_ns = cg.esphome_ns.namespace("ir_learner")
IRLearner = ir_learner_ns.class_("IRLearner", cg.Component)
StatusTrigger = ir_learner_ns.class_("StatusTrigger", automation.Trigger.template(cg.std_string))
LearnedTrigger = ir_learner_ns.class_("LearnedTrigger", automation.Trigger.template(cg.std_string, cg.uint16))
EchoTrigger = ir_learner_ns.class_("EchoTrigger", automation.Trigger.template(cg.std_string, cg.bool_))

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(IRLearner),
        cv.Required(CONF_PIN): pins.internal_gpio_input_pin_schema,
        cv.Required(CONF_TRANSMITTER): cv.use_id(remote_base.RemoteTransmitterBase),
        cv.Optional(CONF_SLOTS, default=24): cv.int_range(min=1, max=64),
        cv.Optional(CONF_MAX_TIMINGS, default=1024): cv.int_range(min=64, max=2048),
        cv.Optional(CONF_END_SILENCE, default="150ms"): cv.positive_time_period_microseconds,
        cv.Optional(CONF_LEARN_TIMEOUT, default="10s"): cv.positive_time_period_milliseconds,
        cv.Optional(CONF_SHORTEST_PULSE, default="100us"): cv.positive_time_period_microseconds,
        cv.Optional(CONF_CARRIER, default="38kHz"): cv.frequency,
        cv.Optional(CONF_ECHO_TOLERANCE, default="40%"): cv.percentage,
        cv.Optional(CONF_ECHO_SLACK, default="150us"): cv.positive_time_period_microseconds,
        cv.Optional(CONF_ON_STATUS): automation.validate_automation(
            {cv.GenerateID(CONF_TRIGGER_ID): cv.declare_id(StatusTrigger)}
        ),
        cv.Optional(CONF_ON_LEARNED): automation.validate_automation(
            {cv.GenerateID(CONF_TRIGGER_ID): cv.declare_id(LearnedTrigger)}
        ),
        cv.Optional(CONF_ON_ECHO): automation.validate_automation(
            {cv.GenerateID(CONF_TRIGGER_ID): cv.declare_id(EchoTrigger)}
        ),
    }
).extend(cv.COMPONENT_SCHEMA)

TRIGGER_ARGUMENTS = {
    CONF_ON_STATUS: [(cg.std_string, "status")],
    CONF_ON_LEARNED: [(cg.std_string, "name"), (cg.uint16, "timings")],
    CONF_ON_ECHO: [(cg.std_string, "name"), (cg.bool_, "confirmed")],
}


async def to_code(config):
    learner = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(learner, config)
    cg.add(learner.set_pin(await cg.gpio_pin_expression(config[CONF_PIN])))
    cg.add(learner.set_transmitter(await cg.get_variable(config[CONF_TRANSMITTER])))
    cg.add(learner.set_slot_count(config[CONF_SLOTS]))
    cg.add(learner.set_max_timings(config[CONF_MAX_TIMINGS]))
    cg.add(learner.set_end_silence_us(config[CONF_END_SILENCE].total_microseconds))
    cg.add(learner.set_learn_timeout_ms(config[CONF_LEARN_TIMEOUT].total_milliseconds))
    cg.add(learner.set_shortest_pulse_us(config[CONF_SHORTEST_PULSE].total_microseconds))
    cg.add(learner.set_carrier_frequency(int(config[CONF_CARRIER])))
    cg.add(learner.set_echo_tolerance(config[CONF_ECHO_TOLERANCE]))
    cg.add(learner.set_echo_slack_us(config[CONF_ECHO_SLACK].total_microseconds))
    for key, arguments in TRIGGER_ARGUMENTS.items():
        for automation_config in config.get(key, []):
            trigger = cg.new_Pvariable(automation_config[CONF_TRIGGER_ID], learner)
            await automation.build_automation(trigger, arguments, automation_config)
