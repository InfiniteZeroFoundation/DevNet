#!/bin/bash

show() {
    set -x
    "$@"
    { set +x; } 2>/dev/null
}




# show python -m dincli.main system dataset distribute-mnist --seed 42 --network local [--clients|--test-train] --num-clients 9 [--task|--model-id 0] 

# show python -m dincli.main system show-index --address 0x145e2dc5C8238d1bE628F87076A37d4a26a78544

show python -m dincli.main system connect-wallet --account 1
show python -m dincli.main model-owner gi start 0



show python -m dincli.main system connect-wallet --account 1
show python -m dincli.main model-owner gi reg aggregators-open 0

show python -m dincli.main system connect-wallet --account 11
show python -m dincli.main aggregator dintoken buy 1 

show python -m dincli.main system connect-wallet --account 12
show python -m dincli.main aggregator dintoken buy 1 --network local

show python -m dincli.main system connect-wallet --account 13
show python -m dincli.main aggregator dintoken buy 1 --network local

show python -m dincli.main system connect-wallet --account 14
show python -m dincli.main aggregator dintoken buy 1 --network local

show python -m dincli.main system connect-wallet --account 15
show python -m dincli.main aggregator dintoken buy 1 --network local

show python -m dincli.main system connect-wallet --account 16
show python -m dincli.main aggregator dintoken buy 1 --network local

show python -m dincli.main system connect-wallet --account 17
show python -m dincli.main aggregator dintoken buy 1 --network local

show python -m dincli.main system connect-wallet --account 18
show python -m dincli.main aggregator dintoken buy 1 --network local

show python -m dincli.main system connect-wallet --account 19
show python -m dincli.main aggregator dintoken buy 1 --network local

show python -m dincli.main system connect-wallet --account 20
show python -m dincli.main aggregator dintoken buy 1 --network local

show python -m dincli.main system connect-wallet --account 21
show python -m dincli.main aggregator dintoken buy 1 --network local

show python -m dincli.main system connect-wallet --account 22
show python -m dincli.main aggregator dintoken buy 1 --network local

show python -m dincli.main system connect-wallet --account 11
show python -m dincli.main aggregator dintoken stake 1000000 --network local

show python -m dincli.main aggregator dintoken read-stake --network local

show python -m dincli.main aggregator register 0


show python -m dincli.main system connect-wallet --account 12
show python -m dincli.main aggregator dintoken stake 1000000 --network local

show python -m dincli.main aggregator dintoken read-stake --network local

show python -m dincli.main aggregator register 0


show python -m dincli.main system connect-wallet --account 13
show python -m dincli.main aggregator dintoken stake 1000000 --network local

show python -m dincli.main aggregator dintoken read-stake --network local

show python -m dincli.main aggregator register 0


show python -m dincli.main system connect-wallet --account 14
show python -m dincli.main aggregator dintoken stake 1000000 --network local

show python -m dincli.main aggregator dintoken read-stake --network local

show python -m dincli.main aggregator register 0


show python -m dincli.main system connect-wallet --account 15
show python -m dincli.main aggregator dintoken stake 1000000 --network local

show python -m dincli.main aggregator dintoken read-stake --network local

show python -m dincli.main aggregator register 0


show python -m dincli.main system connect-wallet --account 16
show python -m dincli.main aggregator dintoken stake 1000000 --network local

show python -m dincli.main aggregator dintoken read-stake --network local

show python -m dincli.main aggregator register 0


show python -m dincli.main system connect-wallet --account 17
show python -m dincli.main aggregator dintoken stake 1000000 --network local

show python -m dincli.main aggregator dintoken read-stake --network local

show python -m dincli.main aggregator register 0


show python -m dincli.main system connect-wallet --account 18
show python -m dincli.main aggregator dintoken stake 1000000 --network local

show python -m dincli.main aggregator dintoken read-stake --network local

show python -m dincli.main aggregator register 0


show python -m dincli.main system connect-wallet --account 19
show python -m dincli.main aggregator dintoken stake 1000000 --network local

show python -m dincli.main aggregator dintoken read-stake --network local

show python -m dincli.main aggregator register 0


show python -m dincli.main system connect-wallet --account 20
show python -m dincli.main aggregator dintoken stake 1000000 --network local

show python -m dincli.main aggregator dintoken read-stake --network local

show python -m dincli.main aggregator register 0


show python -m dincli.main system connect-wallet --account 21
show python -m dincli.main aggregator dintoken stake 1000000 --network local

show python -m dincli.main aggregator dintoken read-stake --network local

show python -m dincli.main aggregator register 0


show python -m dincli.main system connect-wallet --account 22
show python -m dincli.main aggregator dintoken stake 1000000 --network local

show python -m dincli.main aggregator dintoken read-stake --network local

show python -m dincli.main aggregator register 0


show python -m dincli.main system connect-wallet --account 1

show python -m dincli.main model-owner gi show-registered-aggregators 0

show python -m dincli.main model-owner gi reg aggregators-close 0

show python -m dincli.main model-owner gi reg auditors-open 0 

show python -m dincli.main system connect-wallet --account 50
show python -m dincli.main auditor dintoken buy 1 --network local
show python -m dincli.main auditor dintoken stake 1000000 --network local
show python -m dincli.main auditor dintoken read-stake --network local
show python -m dincli.main auditor register 0

show python -m dincli.main system connect-wallet --account 51
show python -m dincli.main auditor dintoken buy 1 --network local
show python -m dincli.main auditor dintoken stake 1000000 --network local
show python -m dincli.main auditor dintoken read-stake --network local
show python -m dincli.main auditor register 0

show python -m dincli.main system connect-wallet --account 52
show python -m dincli.main auditor dintoken buy 1 --network local
show python -m dincli.main auditor dintoken stake 1000000 --network local
show python -m dincli.main auditor dintoken read-stake --network local
show python -m dincli.main auditor register 0

show python -m dincli.main system connect-wallet --account 53
show python -m dincli.main auditor dintoken buy 1 --network local
show python -m dincli.main auditor dintoken stake 1000000 --network local
show python -m dincli.main auditor dintoken read-stake --network local
show python -m dincli.main auditor register 0

show python -m dincli.main system connect-wallet --account 54
show python -m dincli.main auditor dintoken buy 1 --network local
show python -m dincli.main auditor dintoken stake 1000000 --network local
show python -m dincli.main auditor dintoken read-stake --network local
show python -m dincli.main auditor register 0

show python -m dincli.main system connect-wallet --account 55
show python -m dincli.main auditor dintoken buy 1 --network local
show python -m dincli.main auditor dintoken stake 1000000 --network local
show python -m dincli.main auditor dintoken read-stake --network local
show python -m dincli.main auditor register 0

show python -m dincli.main system connect-wallet --account 56
show python -m dincli.main auditor dintoken buy 1 --network local
show python -m dincli.main auditor dintoken stake 1000000 --network local
show python -m dincli.main auditor dintoken read-stake --network local
show python -m dincli.main auditor register 0

show python -m dincli.main system connect-wallet --account 57
show python -m dincli.main auditor dintoken buy 1 --network local
show python -m dincli.main auditor dintoken stake 1000000 --network local
show python -m dincli.main auditor dintoken read-stake --network local
show python -m dincli.main auditor register 0

show python -m dincli.main system connect-wallet --account 58
show python -m dincli.main auditor dintoken buy 1 --network local
show python -m dincli.main auditor dintoken stake 1000000 --network local
show python -m dincli.main auditor dintoken read-stake --network local
show python -m dincli.main auditor register 0

show python -m dincli.main system connect-wallet --account 1

show python -m dincli.main model-owner gi show-registered-auditors 0

show python -m dincli.main model-owner gi reg auditors-close 0

show python -m dincli.main model-owner lms open 0


show python -m dincli.main system connect-wallet --account 2
# show python -m dincli.main client train-lms  0
show python -m dincli.main client train-lms 0 --submit


show python -m dincli.main system connect-wallet --account 3
show python -m dincli.main client train-lms 0 --submit

show python -m dincli.main system connect-wallet --account 4
show python -m dincli.main client train-lms 0 --submit

show python -m dincli.main system connect-wallet --account 5
show python -m dincli.main client train-lms 0 --submit

show python -m dincli.main system connect-wallet --account 6
show python -m dincli.main client train-lms 0 --submit

show python -m dincli.main system connect-wallet --account 7
show python -m dincli.main client train-lms 0 --submit

show python -m dincli.main system connect-wallet --account 8
show python -m dincli.main client train-lms 0 --submit

show python -m dincli.main system connect-wallet --account 9
show python -m dincli.main client train-lms 0 --submit

show python -m dincli.main system connect-wallet --account 10
show python -m dincli.main client train-lms 0 --submit

show python -m dincli.main client lms show-models 0

show python -m dincli.main system connect-wallet --account 1

show python -m dincli.main model-owner lms show-models 0

show python -m dincli.main system connect-wallet --account 1
show python -m dincli.main model-owner lms close 0

show python -m dincli.main system connect-wallet --account 1
show python -m dincli.main model-owner auditor-batches create 0

show python -m dincli.main model-owner auditor-batches show 0

show python -m dincli.main model-owner auditor-batches create-testdataset 0 --submit

show python -m dincli.main model-owner lms-evaluation start 0 

show python -m dincli.main model-owner lms-evaluation show 0 

show python -m dincli.main model-owner lms-evaluation show 0 --auditors --models

show python -m dincli.main system connect-wallet --account 50
show python -m dincli.main auditor lms-evaluation show-batch 0
show python -m dincli.main auditor lms-evaluation evaluate 0 --submit 

show python -m dincli.main system connect-wallet --account 51
show python -m dincli.main auditor lms-evaluation show-batch 0
show python -m dincli.main auditor lms-evaluation evaluate 0 --submit 

show python -m dincli.main system connect-wallet --account 52
show python -m dincli.main auditor lms-evaluation show-batch 0
show python -m dincli.main auditor lms-evaluation evaluate 0 --submit 

show python -m dincli.main system connect-wallet --account 53
show python -m dincli.main auditor lms-evaluation show-batch 0
show python -m dincli.main auditor lms-evaluation evaluate 0 --submit 

show python -m dincli.main system connect-wallet --account 54
show python -m dincli.main auditor lms-evaluation show-batch 0
show python -m dincli.main auditor lms-evaluation evaluate 0 --submit 

show python -m dincli.main system connect-wallet --account 55
show python -m dincli.main auditor lms-evaluation show-batch 0
show python -m dincli.main auditor lms-evaluation evaluate 0 --submit 

show python -m dincli.main system connect-wallet --account 56
show python -m dincli.main auditor lms-evaluation show-batch 0
show python -m dincli.main auditor lms-evaluation evaluate 0 --submit 

show python -m dincli.main system connect-wallet --account 57
show python -m dincli.main auditor lms-evaluation show-batch 0
show python -m dincli.main auditor lms-evaluation evaluate 0 --submit 

show python -m dincli.main system connect-wallet --account 58
show python -m dincli.main auditor lms-evaluation show-batch 0
show python -m dincli.main auditor lms-evaluation evaluate 0 --submit 

show python -m dincli.main system connect-wallet --account 1

show python -m dincli.main model-owner lms-evaluation show 0 --models
show python -m dincli.main model-owner lms-evaluation close 0

show python -m dincli.main model-owner aggregation create-t1nt2-batches 0

show python -m dincli.main model-owner aggregation show-t1-batches 0 --detailed
show python -m dincli.main model-owner aggregation show-t2-batches 0 --detailed

show python -m dincli.main model-owner aggregation T1 start 0

show python -m dincli.main system connect-wallet --account 11
show python -m dincli.main aggregator show-t1-batches 0 --detailed 
show python -m dincli.main aggregator aggregate-t1 0 --submit 

show python -m dincli.main system connect-wallet --account 12
show python -m dincli.main aggregator show-t1-batches 0 --detailed 
show python -m dincli.main aggregator aggregate-t1 0 --submit

show python -m dincli.main system connect-wallet --account 13
show python -m dincli.main aggregator show-t1-batches 0 --detailed 
show python -m dincli.main aggregator aggregate-t1 0 --submit

show python -m dincli.main system connect-wallet --account 14
show python -m dincli.main aggregator show-t1-batches 0 --detailed 
show python -m dincli.main aggregator aggregate-t1 0 --submit

show python -m dincli.main system connect-wallet --account 15
show python -m dincli.main aggregator show-t1-batches 0 --detailed 
show python -m dincli.main aggregator aggregate-t1 0 --submit

show python -m dincli.main system connect-wallet --account 16
show python -m dincli.main aggregator show-t1-batches 0 --detailed 
show python -m dincli.main aggregator aggregate-t1 0 --submit

show python -m dincli.main system connect-wallet --account 17
show python -m dincli.main aggregator show-t1-batches 0 --detailed 
show python -m dincli.main aggregator aggregate-t1 0 --submit

show python -m dincli.main system connect-wallet --account 18
show python -m dincli.main aggregator show-t1-batches 0 --detailed 
show python -m dincli.main aggregator aggregate-t1 0 --submit

show python -m dincli.main system connect-wallet --account 19
show python -m dincli.main aggregator show-t1-batches 0 --detailed 
show python -m dincli.main aggregator aggregate-t1 0 --submit

show python -m dincli.main system connect-wallet --account 20
show python -m dincli.main aggregator show-t1-batches 0 --detailed 
show python -m dincli.main aggregator aggregate-t1 0 --submit

show python -m dincli.main system connect-wallet --account 21
show python -m dincli.main aggregator show-t1-batches 0 --detailed 
show python -m dincli.main aggregator aggregate-t1 0 --submit

show python -m dincli.main system connect-wallet --account 22
show python -m dincli.main aggregator show-t1-batches 0 --detailed 
show python -m dincli.main aggregator aggregate-t1 0 --submit

show python -m dincli.main system connect-wallet --account 1
show python -m dincli.main model-owner aggregation show-t1-batches 0 --detailed 

show python -m dincli.main system connect-wallet --account 1
show python -m dincli.main model-owner aggregation T1 close 0

show python -m dincli.main model-owner aggregation T2 start 0
show python -m dincli.main model-owner gi show-state 0 --network local

show python -m dincli.main model-owner aggregation show-t2-batches 0 --network local --detailed

show python -m dincli.main system connect-wallet --account 11
show python -m dincli.main aggregator show-t2-batches 0 --network local --detailed
show python -m dincli.main aggregator aggregate-t2 0 --submit 

show python -m dincli.main system connect-wallet --account 12
show python -m dincli.main aggregator show-t2-batches 0 --network local --detailed
show python -m dincli.main aggregator aggregate-t2 0 --submit 

show python -m dincli.main system connect-wallet --account 13
show python -m dincli.main aggregator show-t2-batches 0 --network local --detailed
show python -m dincli.main aggregator aggregate-t2 0 --submit 

show python -m dincli.main system connect-wallet --account 14
show python -m dincli.main aggregator show-t2-batches 0 --network local --detailed
show python -m dincli.main aggregator aggregate-t2 0 --submit 

show python -m dincli.main system connect-wallet --account 15
show python -m dincli.main aggregator show-t2-batches 0 --network local --detailed
show python -m dincli.main aggregator aggregate-t2 0 --submit 

show python -m dincli.main system connect-wallet --account 16
show python -m dincli.main aggregator show-t2-batches 0 --network local --detailed
show python -m dincli.main aggregator aggregate-t2 0 --submit 

show python -m dincli.main system connect-wallet --account 17
show python -m dincli.main aggregator show-t2-batches 0 --network local --detailed
show python -m dincli.main aggregator aggregate-t2 0 --submit 

show python -m dincli.main system connect-wallet --account 18
show python -m dincli.main aggregator show-t2-batches 0 --network local --detailed
show python -m dincli.main aggregator aggregate-t2 0 --submit 

show python -m dincli.main system connect-wallet --account 19
show python -m dincli.main aggregator show-t2-batches 0 --network local --detailed
show python -m dincli.main aggregator aggregate-t2 0 --submit 

show python -m dincli.main system connect-wallet --account 20
show python -m dincli.main aggregator show-t2-batches 0 --network local --detailed
show python -m dincli.main aggregator aggregate-t2 0 --submit 

show python -m dincli.main system connect-wallet --account 21
show python -m dincli.main aggregator show-t2-batches 0 --network local --detailed
show python -m dincli.main aggregator aggregate-t2 0 --submit 

show python -m dincli.main system connect-wallet --account 22
show python -m dincli.main aggregator show-t2-batches 0 --network local --detailed
show python -m dincli.main aggregator aggregate-t2 0 --submit 

show python -m dincli.main system connect-wallet --account 1
show python -m dincli.main model-owner aggregation show-t2-batches 0 --network local --detailed

show python -m dincli.main system connect-wallet --account 1
show python -m dincli.main model-owner aggregation T2 close 0

show python -m dincli.main model-owner slash auditors 0 --network local 

show python -m dincli.main model-owner gi show-state 0 --network local 
show python -m dincli.main model-owner slash aggregators 0 --network local 
show python -m dincli.main model-owner gi end 0 --network local 

