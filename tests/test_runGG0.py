import pytest

def test_run_gg0_flow(cli_cmd):
    """
    Replicates the workflow from bashscripts/runGG0.sh
    """

    # show python -m dincli.main system dataset distribute-mnist --seed 42 --clients  "--test-train" --num-clients 9 --model-id 0
    cli_cmd(["system", "dataset", "distribute-mnist", "--seed", "42", "--clients", "--test-train","--num-clients",  "9", "--model-id", "0"])
    
    # 16: show python -m dincli.main system connect-wallet --account 1
    cli_cmd(["system", "connect-wallet", "--account", "1"])
    
    # 17: show python -m dincli.main model-owner gi start 0
    cli_cmd(["model-owner", "gi", "start", "0"])

    # 21: show python -m dincli.main system connect-wallet --account 1
    cli_cmd(["system", "connect-wallet", "--account", "1"])

    # 22: show python -m dincli.main model-owner gi reg aggregators-open 0
    cli_cmd(["model-owner", "gi", "reg", "aggregators-open", "0"])

    # Aggregators Buy loop (Accounts 11-22)
    # Lines 24-59
    aggregator_accounts = range(11, 23) # 11 to 22
    for acc in aggregator_accounts:
        cli_cmd(["system", "connect-wallet", "--account", str(acc)])
        cli_cmd(["aggregator", "dintoken", "buy", "1"])
        cli_cmd(["aggregator", "dintoken", "stake", "1000000"])
        cli_cmd(["aggregator", "dintoken", "read-stake"])
        cli_cmd(["aggregator", "register", "0"])

    # 156: show python -m dincli.main system connect-wallet --account 1
    cli_cmd(["system", "connect-wallet", "--account", "1"])

    # 158: show python -m dincli.main model-owner gi show-registered-aggregators 0
    cli_cmd(["model-owner", "gi", "show-registered-aggregators", "0"])

    # 160: show python -m dincli.main model-owner gi reg aggregators-close 0
    cli_cmd(["model-owner", "gi", "reg", "aggregators-close", "0"])

    # 162: show python -m dincli.main model-owner gi reg auditors-open 0 
    cli_cmd(["model-owner", "gi", "reg", "auditors-open", "0"])

    # Auditors Loop (Accounts 50-58)
    # Lines 164-216
    auditor_accounts = range(50, 59) # 50 to 58
    for acc in auditor_accounts:
        cli_cmd(["system", "connect-wallet", "--account", str(acc)])
        cli_cmd(["auditor", "dintoken", "buy", "1"])
        cli_cmd(["auditor", "dintoken", "stake", "1000000"])
        cli_cmd(["auditor", "dintoken", "read-stake"])
        cli_cmd(["auditor", "register", "0"])

    # 218: show python -m dincli.main system connect-wallet --account 1
    cli_cmd(["system", "connect-wallet", "--account", "1"])

    # 220: show python -m dincli.main model-owner gi show-registered-auditors 0
    cli_cmd(["model-owner", "gi", "show-registered-auditors", "0"])

    # 222: show python -m dincli.main model-owner gi reg auditors-close 0
    cli_cmd(["model-owner", "gi", "reg", "auditors-close", "0"])

    # 224: show python -m dincli.main model-owner lms open 0
    cli_cmd(["model-owner", "lms", "open", "0"])

    # Clients Train Loop (Accounts 2-10)
    # Lines 227-254
    client_accounts = range(2, 11) # 2 to 10
    for acc in client_accounts:
        cli_cmd(["system", "connect-wallet", "--account", str(acc)])
        cli_cmd(["client", "train-lms", "0", "--submit"])
        
    # 256: show python -m dincli.main client lms show-models 0
    cli_cmd(["client", "lms", "show-models", "0"])

    # 258: show python -m dincli.main system connect-wallet --account 1
    cli_cmd(["system", "connect-wallet", "--account", "1"])
    
    # 260: show python -m dincli.main model-owner lms show-models 0
    cli_cmd(["model-owner", "lms", "show-models", "0"])

    # 263: show python -m dincli.main model-owner lms close 0
    cli_cmd(["model-owner", "lms", "close", "0"])

    # 266: show python -m dincli.main model-owner auditor-batches create 0
    cli_cmd(["model-owner", "auditor-batches", "create", "0"])

    # 268: show python -m dincli.main model-owner auditor-batches show 0
    cli_cmd(["model-owner", "auditor-batches", "show", "0"])

    # 270: show python -m dincli.main model-owner auditor-batches create-testdataset 0 --submit
    cli_cmd(["model-owner", "auditor-batches", "create-testdataset", "0", "--submit"])

    # 272: show python -m dincli.main model-owner lms-evaluation start 0 
    cli_cmd(["model-owner", "lms-evaluation", "start", "0"])

    # 274: show python -m dincli.main model-owner lms-evaluation show 0 
    cli_cmd(["model-owner", "lms-evaluation", "show", "0"])

    # 276: show python -m dincli.main model-owner lms-evaluation show 0 --auditors --models
    cli_cmd(["model-owner", "lms-evaluation", "show", "0", "--auditors", "--models"])

    # Auditors Evaluation Loop (Accounts 50-58)
    # Lines 278-312
    for acc in auditor_accounts:
        cli_cmd(["system", "connect-wallet", "--account", str(acc)])
        cli_cmd(["auditor", "lms-evaluation", "show-batch", "0"])
        cli_cmd(["auditor", "lms-evaluation", "evaluate", "0", "--submit"])

    # 314: show python -m dincli.main system connect-wallet --account 1
    cli_cmd(["system", "connect-wallet", "--account", "1"])

    # 316: show python -m dincli.main model-owner lms-evaluation show 0 --models
    cli_cmd(["model-owner", "lms-evaluation", "show", "0", "--models"])

    # 317: show python -m dincli.main model-owner lms-evaluation close 0
    cli_cmd(["model-owner", "lms-evaluation", "close", "0"])

    # 319: show python -m dincli.main model-owner aggregation create-t1nt2-batches 0
    cli_cmd(["model-owner", "aggregation", "create-t1nt2-batches", "0"])

    # 321: show python -m dincli.main model-owner aggregation show-t1-batches 0 --detailed
    cli_cmd(["model-owner", "aggregation", "show-t1-batches", "0", "--detailed"])

    # 322: show python -m dincli.main model-owner aggregation show-t2-batches 0 --detailed
    cli_cmd(["model-owner", "aggregation", "show-t2-batches", "0", "--detailed"])

    # 324: show python -m dincli.main model-owner aggregation T1 start 0
    cli_cmd(["model-owner", "aggregation", "T1", "start", "0"])

    # Aggregators T1 Loop (Accounts 11-22)
    # Lines 326-372
    for acc in aggregator_accounts:
        cli_cmd(["system", "connect-wallet", "--account", str(acc)])
        cli_cmd(["aggregator", "show-t1-batches", "0", "--detailed"])
        cli_cmd(["aggregator", "aggregate-t1", "0", "--submit"])

    # 374: show python -m dincli.main system connect-wallet --account 1
    cli_cmd(["system", "connect-wallet", "--account", "1"])
    
    # 375: show python -m dincli.main model-owner aggregation show-t1-batches 0 --detailed 
    cli_cmd(["model-owner", "aggregation", "show-t1-batches", "0", "--detailed"])

    # 378: show python -m dincli.main model-owner aggregation T1 close 0
    cli_cmd(["model-owner", "aggregation", "T1", "close", "0"])

    # 380: show python -m dincli.main model-owner aggregation T2 start 0
    cli_cmd(["model-owner", "aggregation", "T2", "start", "0"])
    
    # 381: show python -m dincli.main model-owner gi show-state 0 --network local
    cli_cmd(["model-owner", "gi", "show-state", "0"])

    # 383: show python -m dincli.main model-owner aggregation show-t2-batches 0 --network local --detailed
    cli_cmd(["model-owner", "aggregation", "show-t2-batches", "0", "--detailed"])

    # Aggregators T2 Loop (Accounts 11-22)
    # Lines 385-431
    for acc in aggregator_accounts:
        cli_cmd(["system", "connect-wallet", "--account", str(acc)])
        cli_cmd(["aggregator", "show-t2-batches", "0", "--detailed"])
        cli_cmd(["aggregator", "aggregate-t2", "0", "--submit"])

    # 433: show python -m dincli.main system connect-wallet --account 1
    cli_cmd(["system", "connect-wallet", "--account", "1"])
    
    # 434: show python -m dincli.main model-owner aggregation show-t2-batches 0 --network local --detailed
    cli_cmd(["model-owner", "aggregation", "show-t2-batches", "0", "--detailed"])

    # 437: show python -m dincli.main model-owner aggregation T2 close 0
    cli_cmd(["model-owner", "aggregation", "T2", "close", "0"])

    # 439: show python -m dincli.main model-owner slash auditors 0 --network local 
    cli_cmd(["model-owner", "slash", "auditors", "0"])

    # 441: show python -m dincli.main model-owner gi show-state 0 --network local 
    cli_cmd(["model-owner", "gi", "show-state", "0"])

    # 442: show python -m dincli.main model-owner slash aggregators 0 --network local 
    cli_cmd(["model-owner", "slash", "aggregators", "0"])

    # 443: show python -m dincli.main model-owner gi end 0 --network local 
    cli_cmd(["model-owner", "gi", "end", "0"])
