import setting
import runtime
import logging
import re
import opcodes
import executor
import util
import z3
import os
import tempfile
from basic_class import BasicBlock, Timeout, Configuration

log = logging.getLogger(__name__)


# A simple lexer that parses instructions into the dict type
def parse_instructions():
    labels = []
    line_number = 1
    address = 0
    reach_file_end = False
    with open(setting.SOURCE_FILENAME, 'r') as teal_file:
        version_split = teal_file.readline().split("#pragma version")

        if len(version_split) < 2:
            log.error("Unable to resolve TEAL version")
            exit(runtime.PARSE_INSTRUCTIONS_FAILED)
        else:
            runtime.version = int(version_split[1].strip())
            if runtime.version > 8:
                log.error("Unsupported TEAL version")
                exit(runtime.PARSE_INSTRUCTIONS_FAILED)
        
        while True:
            line_number += 1
            token = teal_file.readline()
            
            if reach_file_end == True:
                break

            # Add a return opcode at the end of the file
            if not token:
                token = "return"
                reach_file_end = True
            
            if len(token.strip()) == 0:
                continue
            if token.strip().startswith("//"):
                continue
            token = token.strip()

            if "//" in token:
                byte_match = re.match("^(byte \".*\")", token)
                pushbytes_match = re.match("^(pushbytes \".*\")", token)
                if byte_match != None:
                    message = token.split(byte_match.group(1))[1]
                elif pushbytes_match != None:
                    message = token.split(pushbytes_match.group(1))[1]
                else:
                    message = token
                
                if "//" in message:
                    comment = message.split("//")[1]
                    token = token.split("//" + comment)[0].strip()
                else:
                    comment = None
            else:
                comment = None
            
            # The label will associate with the next instruction
            label = re.match("^([a-zA-Z0-9_]+):",token)
            if label:
                labels.append(label.groups()[0])
                continue
            
            if len(labels) > 1:
                log.error("Multiple tags found at line {}".format(line_number))
                exit(runtime.PARSE_INSTRUCTIONS_FAILED)
            if len(labels) == 1:
                label = labels[0]
                labels = []
            else:
                label = None
            
            if len(token.split(" ")) > 1:
                params = token.split(" ")[1:]
            else:
                params = []

            opcode_type = token.split(" ")[0].strip()
            if runtime.app_call_group_index == -1:
                # Check whether each opcode is legal
                if opcodes.params_number(opcode_type) != len(params) and opcodes.params_number(opcode_type) != -1:
                    log.error("Opcode ({}) parameter numbers mismatch at line {}".format(opcode_type, line_number))
                    exit(runtime.PARSE_INSTRUCTIONS_FAILED)
                if setting.IS_SMART_CONTRACT and not opcodes.support_application_mode(opcode_type):
                    log.error("Opcode does not support application mode at line {}".format(line_number))
                    exit(runtime.PARSE_INSTRUCTIONS_FAILED)
                if setting.IS_LOGIC_SIGNATURE and not opcodes.support_signature_mode(opcode_type):
                    log.error("Opcode does not support signature mode at line {}".format(line_number))
                    exit(runtime.PARSE_INSTRUCTIONS_FAILED)
            
            instruction = {
                "type": opcode_type,
                "params": params,
                "address": address,
                "label": label,
                "comment": comment,
                "line_number": line_number
            }
            runtime.instructions[address] = instruction
            address += 1

    if len(labels) > 0: # Never reach
        log.error("TEAL file ends with labels")
        exit(runtime.PARSE_INSTRUCTIONS_FAILED)

# Change the format of jump instructions, i.e., bnz <label> ---> bnz <address>
# Address represents the position of the instruction in runtime.instructions
def parse_labels():
    for address in runtime.instructions:
        instruction = runtime.instructions[address]
        if instruction["label"] != None:
            label = instruction["label"]
            runtime.labels[label] = instruction["address"]
    for address in runtime.instructions:
        instruction = runtime.instructions[address]
        if instruction["type"] in ["bnz", "bz", "b", "callsub"]:
            label = instruction["params"][0]
            if label not in runtime.labels:
                log.error("Invalid label at line {}".format(instruction["line_number"]))
                exit(runtime.PARSE_LABELS_FAILED)
            instruction["dest_label"] = label
            instruction["params"] = [str(runtime.labels[label])]
        elif instruction["type"] == "switch":
            for index in range(len(instruction["params"])):
                label = instruction["params"][index]
                if label not in runtime.labels:
                    log.error("Invalid label at line {}".format(instruction["line_number"]))
                    exit(runtime.PARSE_LABELS_FAILED)
                #instruction["dest_labels"][index] = label
                instruction["params"][index] = str(runtime.labels[label])


def construct_basic_block():
    current_block_instructions = {}
    for address in runtime.instructions:
        instruction = runtime.instructions[address]
        if instruction["label"] != None:
            if len(current_block_instructions) > 0:
                block = BasicBlock(current_block_instructions)
                runtime.vertices[block.start_address] = block
                current_block_instructions = {}
            current_block_instructions[address] = instruction
        if instruction["type"] in ["bnz", "bz", "b", "callsub", "retsub"]:
            current_block_instructions[address] = instruction
            block = BasicBlock(current_block_instructions)
            runtime.vertices[block.start_address] = block
            current_block_instructions = {}
        else:
            current_block_instructions[address] = instruction
    if len(current_block_instructions) > 0:
        block = BasicBlock(current_block_instructions)
        runtime.vertices[block.start_address] = block

    # Check the correctness of the basic block construction
    for instruction in runtime.instructions.values():
        if instruction["type"] in ["bnz", "bz", "b", "callsub"]:
            target = int(instruction["params"][0])
            if target not in runtime.vertices:
                log.critical("Fail to check the correctness of the basic block construction")
                log.debug("instruction line number: {} , targe: {}".format(instruction["line_number"], target))
                exit(runtime.INCORRECT_BLOCK_CONSTRUCTION)
    end_block_number = 0
    for block in runtime.vertices.values():
        if block.adjacent_block_address == -1:
            end_block_number += 1
    if end_block_number != 1:
        log.critical("Multiple end blocks detected")
        exit(runtime.INCORRECT_BLOCK_CONSTRUCTION)

def format_instructions():
    for address in runtime.instructions:
        instruction = runtime.instructions[address]
        if instruction["type"] == "int":
            instruction["params"] = [opcodes.get_string_constant(instruction["params"][0])]


# Currently we use pattern matching to detect the validator.
# TODO: solve the symbolic variables for more accurate detection.
def include_app():
    file_content = open(setting.SOURCE_FILENAME, 'r').read()
    app_index = -1
    app_id = -1
    global_state = None

    result = re.search("txn ApplicationID\nintc_([0-9]).*\n==", file_content)
    if result != None:
        group_index = -2
        app_index = int(result.group(1))
    
    result = re.search("txn ApplicationID\nintc ([0-9]+).*\n==", file_content)
    if result != None:
        group_index = -2
        app_index = int(result.group(1))

    result = re.search("txn ApplicationID\npushint ([0-9]+).*\n==", file_content)
    if result != None:
        group_index = -2
        app_id = int(result.group(1))
    
    result = re.search("gtxns ApplicationID\nintc_([0-9]).*\n==", file_content)
    if result != None:
        group_index = -3
        app_index = int(result.group(1))
    
    result = re.search("gtxns ApplicationID\nintc ([0-9]+).*\n==", file_content)
    if result != None:
        group_index = -3
        app_index = int(result.group(1))

    result = re.search("gtxns ApplicationID\npushint ([0-9]+).*\n==", file_content)
    if result != None:
        group_index = -3
        app_id = int(result.group(1))

    result = re.search("gtxn ([0-9]+) ApplicationID\nintc_([0-9]).*\n==", file_content)
    if result != None:
        group_index = int(result.group(1))
        app_index = int(result.group(2))
    
    result = re.search("gtxn ([0-9]+) ApplicationID\nintc ([0-9]+).*\n==", file_content)
    if result != None:
        group_index = int(result.group(1))
        app_index = int(result.group(2))

    result = re.search("gtxn ([0-9]+) ApplicationID\npushint ([0-9]+).*\n==", file_content)
    if result != None:
        group_index = int(result.group(1))
        app_id = int(result.group(2))

    if app_index == -1 and app_id == -1:
        if "ApplicationID" in file_content:
            log.critical("Validator exists but failed to fetch")
            exit(runtime.INCLUDE_VALIDATOR_FAILED)
        log.info("Validator does not exists")
        return None
        
    if app_id == -1:
        try:
            intcblock = re.search("intcblock(.*)\n", file_content).group(1).split(" ")[1:]
            app_id = int(intcblock[app_index])
        except:
            log.info("Fail to parse intcblock")
            return None

    try:
        # Get the latest version
        approval_file_name, global_state = util.read_app_info(app_id, force = False)

        if approval_file_name == None:
            log.info("App does not exists: {}".format(app_id))
            log.info("Try to include the historical version")

            # Get the historical version if the app is deleted
            approval_file_name = util.get_app(app_id)
    except:
        log.info("Failed to include the validator")
        return None
    app_content = open(approval_file_name, 'r').read()
    if not file_content.endswith("return"):
        file_content += "\nreturn"
    
    file_content = file_content.replace("label", "sig_label")
    file_content = file_content.replace("return", "bnz app_label\nerr")
    file_content += "\napp_label:\n"
    app_content = "\n".join(app_content.split("\n")[1:])
    new_content = file_content + app_content
    os.unlink(approval_file_name)

    runtime.app_call_group_index = group_index

    with tempfile.NamedTemporaryFile(delete=False, mode="w") as tmp:
        tmp.write(new_content)
        print("Include appID: {}".format(app_id), flush=True)
        setting.SOURCE_FILENAME = tmp.name
        print("Recombined File:", tmp.name)
    return global_state
    

def initialize_symbolic_environment():
    global initial_configuration
    initial_configuration = Configuration()
    if setting.IS_LOGIC_SIGNATURE:
        runtime.lsig_address = util.get_lsig_address(open(setting.SOURCE_FILENAME, 'r').read())
    
    # Include the code of the validator in signature mode
    if setting.INCLUDE_APP:
        global_state = include_app()
        if global_state != None and setting.LOAD_STATE == True:
            for key in global_state:
                if global_state[key]["type"] == "uint":
                    initial_configuration.global_state_return_uint = z3.Store(initial_configuration.global_state_return_uint, 
                                                    z3.StringVal(key), global_state[key]["value"])
                if global_state[key]["type"] == "bytes":
                    initial_configuration.global_state_return_bytes = z3.Store(initial_configuration.global_state_return_bytes, 
                                                    z3.StringVal(key), global_state[key]["value"])

    if setting.APPLICATION_ID != 0:
        approval_file_name, global_state = util.read_app_info(setting.APPLICATION_ID)
        setting.SOURCE_FILENAME = approval_file_name
        for key in global_state:
            if global_state[key]["type"] == "uint":
                initial_configuration.global_state_return_uint = z3.Store(initial_configuration.global_state_return_uint, 
                                                z3.StringVal(key), global_state[key]["value"])
            if global_state[key]["type"] == "bytes":
                initial_configuration.global_state_return_bytes = z3.Store(initial_configuration.global_state_return_bytes, 
                                                z3.StringVal(key), global_state[key]["value"])

    # Scratch locations are initialized as uint64 zero
    for key in range(256):
        initial_configuration.scratch_space_return_uint = z3.Store(initial_configuration.scratch_space_return_uint, z3.BitVecVal(key,64), z3.BitVecVal(0,64))
        initial_configuration.scratch_space_return_bytes = z3.Store(initial_configuration.scratch_space_return_bytes, z3.BitVecVal(key,64), z3.StringVal(""))


def analysis_entry_point():
    initialize_symbolic_environment()
    parse_instructions()
    parse_labels()
    format_instructions()
    construct_basic_block()
    executor.symbolic_execute_block(initial_configuration)

def run():
    with Timeout(sec=setting.GLOBAL_TIMEOUT):
        analysis_entry_point()
    runtime.end_process()

