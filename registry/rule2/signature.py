
import z3
import runtime
import memory
import logging
from ..parser import *

log = logging.getLogger(__name__)


def unchecked_transaction_fee_in_lsig(configuration):
    if is_constrained_var("gtxn_Fee[GroupIndex]") == True:
        return False
    else:
        if configuration.app_area == True:
            index_string = runtime.get_group_index_string(configuration)
            if is_constrained_var("gtxn_Sender[{}]".format(index_string)) == True:
                return False
        
        gtxn_index_list = list(set(configuration.opcode_record["gtxn_index"]))
        constraint = len(gtxn_index_list) < z3.BitVec("global_GroupSize", 64)
        if runtime.solver.satisfy(constraint) == z3.sat:
            return True

        for index in gtxn_index_list:
            if is_constrained_var("gtxn_Fee[{}]".format(index)) == False:
                current_constraint = z3.And(
                                        z3.Select(memory.gtxn_Sender, index) == z3.StringVal( runtime.lsig_address ),
                                        z3.BitVec("GroupIndex", 64) == index
                                    )

                if runtime.solver.satisfy(current_constraint) == z3.sat:
                    print("\033[1;33;47mUnchecked transaction fee index: {}\033[0m".format(index))
                    return True
        return False



def unchecked_RekeyTo_in_lsig(configuration):

    # It seems that TEAL version 1 does not support rekey-to
    if runtime.version > 1:
        if is_constrained_var("gtxn_RekeyTo[GroupIndex]") == True:
            return False
        else:
            current_constraint = z3.And(z3.Select(memory.gtxn_CloseRemainderTo, z3.BitVec("GroupIndex", 64)) == z3.StringVal( "\x00" * 32 ),
                                    z3.Select(memory.gtxn_AssetCloseTo, z3.BitVec("GroupIndex", 64)) == z3.StringVal( "\x00" * 32 ) )
            if runtime.solver.satisfy(current_constraint) != z3.sat:
                return False

            if configuration.app_area == True:
                index_string = runtime.get_group_index_string(configuration)
                if is_constrained_var("gtxn_Sender[{}]".format(index_string)) == True:
                    return False
            
            gtxn_index_list = list(set(configuration.opcode_record["gtxn_index"]))
            constraint = len(gtxn_index_list) < z3.BitVec("global_GroupSize", 64)
            if runtime.solver.satisfy(constraint) == z3.sat:
                return True

            for index in gtxn_index_list:
                if is_constrained_var("gtxn_RekeyTo[{}]".format(index)) == False:
                    current_constraint = z3.And(z3.Select(memory.gtxn_Sender, index) == z3.StringVal( runtime.lsig_address ),
                                    z3.BitVec("GroupIndex", 64) == index,
                                    z3.Select(memory.gtxn_CloseRemainderTo, index) == z3.StringVal( "\x00" * 32 ),
                                    z3.Select(memory.gtxn_AssetCloseTo, index) == z3.StringVal( "\x00" * 32 ) )
                
                    if runtime.solver.satisfy(current_constraint) == z3.sat:
                        print("\033[1;32;47mUnchecked RekeyTo index: {}\033[0m".format(index))
                        return True
            return False
    else:
        return False



def unchecked_CloseRemainderTo_in_lsig(configuration):
    if is_constrained_var("gtxn_CloseRemainderTo[GroupIndex]") == True:
        return False
    else:
        current_constraint = z3.And(z3.Select(memory.gtxn_TypeEnum, z3.BitVec("GroupIndex", 64)) == 1,
                                z3.Select(memory.gtxn_Type, z3.BitVec("GroupIndex", 64)) == z3.StringVal( "pay" ) )
        if runtime.solver.satisfy(current_constraint) != z3.sat:
            return False

        # Check the implicit transaction type
        if is_payment_transaction("GroupIndex") == False:
            return False

        if configuration.app_area == True:
            index_string = runtime.get_group_index_string(configuration)
            if is_constrained_var("gtxn_Sender[{}]".format(index_string)) == True:
                return False

        gtxn_index_list = list(set(configuration.opcode_record["gtxn_index"]))
        constraint = len(gtxn_index_list) < z3.BitVec("global_GroupSize", 64)
        if runtime.solver.satisfy(constraint) == z3.sat:
            return True

        for index in gtxn_index_list:

            # Check the implicit transaction type
            if is_payment_transaction(index) == False:
                continue


            if is_constrained_var("gtxn_CloseRemainderTo[{}]".format(index)) == False:
                current_constraint = z3.And(z3.Select(memory.gtxn_TypeEnum, index) == 1,
                                z3.Select(memory.gtxn_Type, index) == z3.StringVal( "pay" ),
                                z3.Select(memory.gtxn_Sender, index) == z3.StringVal( runtime.lsig_address ),
                                z3.BitVec("GroupIndex", 64) == index )

                if runtime.solver.satisfy(current_constraint) == z3.sat:
                    print("\033[1;32;47mUnchecked CloseRemainderTo index: {}\033[0m".format(index))
                    return True
        return False


def unchecked_AssetCloseTo_in_lsig(configuration):
    if is_constrained_var("gtxn_AssetCloseTo[GroupIndex]") == True:
        return False
    else:
        current_constraint = z3.And(z3.Select(memory.gtxn_TypeEnum, z3.BitVec("GroupIndex", 64)) == 4,
                                z3.Select(memory.gtxn_Type, z3.BitVec("GroupIndex", 64)) == z3.StringVal( "axfer" ) )
        if runtime.solver.satisfy(current_constraint) != z3.sat:
            return False

        # Check the implicit transaction type
        if is_asset_transfer_transaction("GroupIndex") == False:
            return False

        if configuration.app_area == True:
            index_string = runtime.get_group_index_string(configuration)
            if is_constrained_var("gtxn_Sender[{}]".format(index_string)) == True:
                return False

        gtxn_index_list = list(set(configuration.opcode_record["gtxn_index"]))
        constraint = len(gtxn_index_list) < z3.BitVec("global_GroupSize", 64)
        if runtime.solver.satisfy(constraint) == z3.sat:
            return True
        
        for index in gtxn_index_list:

            # Check the implicit transaction type
            if is_asset_transfer_transaction(index) == False:
                continue

            if is_constrained_var("gtxn_AssetCloseTo[{}]".format(index)) == False:
                current_constraint = z3.And(z3.Select(memory.gtxn_TypeEnum, index) == 4,
                                z3.Select(memory.gtxn_Type, index) == z3.StringVal( "axfer" ),
                                z3.Select(memory.gtxn_AssetSender, index) == z3.StringVal( runtime.lsig_address ),
                                z3.BitVec("GroupIndex", 64) == index,

                                # Exclude the Asset Accept Transaction and Asset Clawback Transaction
                                z3.Select(memory.gtxn_Sender, index) == z3.StringVal( "\x00" * 32 ) )

                if runtime.solver.satisfy(current_constraint) == z3.sat:
                    print("\033[1;32;47mUnchecked AssetCloseTo index: {}\033[0m".format(index))
                    return True
        return False


def smart_signature_arbitrary_spend_vulnerability(configuration):
    if configuration.symbolic_hash_variable_used == True:
        return False

    if configuration.opcode_record["app_local_get"] == True:
        return False
    
    if configuration.app_area == True:
        index_string = runtime.get_group_index_string(configuration)
        if is_constrained_var("gtxn_Sender[{}]".format(index_string)) == True:
            return False
    
    current_constraint = [
            z3.Select(memory.gtxn_Sender, z3.BitVec("GroupIndex", 64)) == z3.StringVal( runtime.lsig_address ),
            z3.Select(memory.gtxn_AssetSender, z3.BitVec("GroupIndex", 64)) == z3.StringVal( runtime.lsig_address ),
            z3.Select(memory.gtxn_Fee, z3.BitVec("GroupIndex", 64)) >= z3.BitVecVal( 1000, 64 )
    ]
    gtxn_index_list = list(set(configuration.opcode_record["gtxn_index"]))
    if len(gtxn_index_list) == 0:
        if runtime.solver.satisfy(current_constraint) == z3.sat:
            print("\033[1;32;47mSmart signature arbitrary spend index: GroupIndex\033[0m")
            return True

    current_constraint = [
            z3.Select(memory.gtxn_Amount, z3.BitVec("GroupIndex", 64)) > z3.BitVecVal( 100000 * 1000000, 64 )
    ]
    if runtime.solver.satisfy(current_constraint) == z3.sat:
        return False

    for index in gtxn_index_list:
        current_constraint = [
            z3.Select(memory.gtxn_Amount, index) > z3.BitVecVal( 100000 * 1000000, 64 )
        ]
        if runtime.solver.satisfy(current_constraint) == z3.sat:
            return False
    
    for index in gtxn_index_list:
        current_constraint = [
            z3.Select(memory.gtxn_Sender, index) == z3.StringVal( runtime.lsig_address ),
            z3.Select(memory.gtxn_AssetSender, index) == z3.StringVal( runtime.lsig_address ),
            z3.Select(memory.gtxn_Fee, index) >= z3.BitVecVal( len(gtxn_index_list) * 1000, 64 )
        ]
        if runtime.solver.satisfy(current_constraint) == z3.sat and check_txn_sender(gtxn_index_list, index):
            print("\033[1;32;47mSmart signature arbitrary spend index: {}\033[0m".format(index))
            return True

    return False
