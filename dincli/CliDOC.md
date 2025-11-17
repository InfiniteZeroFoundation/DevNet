dincli --help
dincli --version


dincli connect-wallet <0xprivatekey>

dincli reset-all
dincli reset <FL_task_Coordinator_Address>

dincli --network

dincli distribute-mnist-dataset --clients 9

dincli --usdt-info
dincli --dinCoordinator-info --network <network|local|sepolia|mainnet>
dincli --dinStake-info --network <network|local|sepolia|mainnet>
dincli --dinToken-info --network <network|local|sepolia|mainnet>
dincli dinRepresentative-info --network <network|local|sepolia|mainnet>
dincli dindao  deploy-dinCoordinator --network <network|local|sepolia|mainnet>
dincli dindao deploy-dinToken --network <network|local|sepolia|mainnet> --dinCoordinator-address <dinCoordinator-address>
dincli dindao  deploy-dinStake --network <network|local|sepolia|mainnet> --dinCoordinator-address <dinCoordinator-address> --dinToken-address <dinToken-address>
dincli dindao add-slasher --dinTaskCoordinator-address <dinTaskCoordinator-address> --network <network|local|sepolia|mainnet>
dincli dindao add-slasher --dinTaskAuditor-address <dinTaskAuditor-address>  --network <network|local|sepolia|mainnet>


dincli modelowner buy-usdt <USDT-Amount> --network <network|local|sepolia|mainnet>
dincli modelowner deploy-dinTaskCoordinator --network <network|local|sepolia|mainnet>
dincli modelowner deploy-dinTaskAuditor --network <network|local|sepolia|mainnet> --dinTaskCoordinator-Address <dinTaskCoordinator-Address> 
dincli modelowner depositUSTD-dinTaskAuditor --network <network|local|sepolia|mainnet> --dinTaskAuditor-Address <dinTaskAuditor-Address> <Amount>
dincli modelowner add-slasher --network <network|local|sepolia|mainnet> --dinTaskCoordinator-Address <dinTaskCoordinator-Address> 
dincli modelowner add-slasher --network <network|local|sepolia|mainnet> --dinTaskAuditor-Address <dinTaskAuditor-Address> 
dincli modelowner create-genesis-model <ipfs-hash> --dinTaskCoordinator-Address <dinTaskCoordinator-Address>  --network <network|local|sepolia|mainnet>
dincli modelowner strart-GI <GI> --dinTaskCoordinator-Address <dinTaskCoordinator-Address>  --network <network|local|sepolia|mainnet>
dincli modelowner strart-DIN-Aggregators-registration <GI> --dinTaskCoordinator-Address <dinTaskCoordinator-Address>  --network <network|local|sepolia|mainnet>
dincli modelowner strart-DIN-Auditors-registration <GI> --dinTaskCoordinator-Address <dinTaskCoordinator-Address>  --network <network|local|sepolia|mainnet>
dincli modelowner close-DIN-Aggregators-registration <GI> --dinTaskCoordinator-Address <dinTaskCoordinator-Address>  --network <network|local|sepolia|mainnet>
dincli modelowner close-DIN-Auditors-registration <GI> --dinTaskCoordinator-Address <dinTaskCoordinator-Address>  --network <network|local|sepolia|mainnet>
dincli modelowner start-DIN-LM-Submissions <GI> --dinTaskAuditor-Address <dinTaskAuditor-Address>  --network <network|local|sepolia|mainnet>
dincli modelowner show-LMS <GI> --dinTaskAuditor-Address <dinTaskAuditor-Address>  --network <network|local|sepolia|mainnet>
dincli modelowner close-DIN-LM-Submissions <GI> --dinTaskAuditor-Address <dinTaskAuditor-Address>  --network <network|local|sepolia|mainnet>
dincli modelowner create-DIN-Auditor-Batches <GI> --dinTaskAuditor-Address <dinTaskAuditor-Address>  --network <network|local|sepolia|mainnet>
dincli modelowner Assign-TestCID-DIN-Auditor-Batch <GI> --dinTaskAuditor-Address <dinTaskAuditor-Address> --BatchIndex <BatchIndex> --network <network|local|sepolia|mainnet>
dincli modelowner start-LMS-evaluation <GI> --dinTaskAuditor-Address <dinTaskAuditor-Address>  --network <network|local|sepolia|mainnet>
dincli modelowner close-LMS-evaluation <GI> --dinTaskAuditor-Address <dinTaskAuditor-Address>  --network <network|local|sepolia|mainnet>
dincli modelowner create-T1nT2-AggregationBatches <GI> --dinTaskCoordinator-Address <dinTaskCoordinator-Address>  --network <network|local|sepolia|mainnet>
dincli modelowner start-T1-Aggregation <GI> --dinTaskCoordinator-Address <dinTaskCoordinator-Address>  --network <network|local|sepolia|mainnet>
dincli modelowner finalize-T1-Aggregation <GI> --dinTaskCoordinator-Address <dinTaskCoordinator-Address>  --network <network|local|sepolia|mainnet>
dincli modelowner start-T2-Aggregation <GI> --dinTaskCoordinator-Address <dinTaskCoordinator-Address>  --network <network|local|sepolia|mainnet>
dincli modelowner finalize-T2-Aggregation <GI> --dinTaskCoordinator-Address <dinTaskCoordinator-Address>  --network <network|local|sepolia|mainnet>
dincli modelowner slash-Auditors <GI> --dinTaskCoordinator-Address <dinTaskCoordinator-Address>  --network <network|local|sepolia|mainnet>
dincli modelowner slash-Aggregators <GI> --dinTaskCoordinator-Address <dinTaskCoordinator-Address>  --network <network|local|sepolia|mainnet>
dincli modelowner end-GI <GI> --dinTaskCoordinator-Address <dinTaskCoordinator-Address>  --network <network|local|sepolia|mainnet>

dincli aggregator buy-DINtokens <Amount> --network <network|local|sepolia|mainnet>
dincli aggregator stake-DINtokens <Amount> --network <network|local|sepolia|mainnet>
dincli aggregator registerAsAggregator <GI> --dinTaskCoordinator-Address <dinTaskCoordinator-Address> --network <network|local|sepolia|mainnet>
dincli aggregator getmyT1batch <GI> --dinTaskCoordinator-Address <dinTaskCoordinator-Address> --network <network|local|sepolia|mainnet>
dincli aggregator AggregateT1Batch <IPFShash> <GI> --aggregationScheme <aggregationScheme> --dinTaskCoordinator-Address <dinTaskCoordinator-Address> --network <network|local|sepolia|mainnet>
dincli aggregator getmyT2batch <GI> --dinTaskCoordinator-Address <dinTaskCoordinator-Address> --network <network|local|sepolia|mainnet>
dincli aggregator AggregateT2batch <IPFShash> <GI> --aggregationScheme <aggregationScheme> --dinTaskCoordinator-Address <dinTaskCoordinator-Address> --network <network|local|sepolia|mainnet>


dincli auditor buy-DINtokens <Amount> --network <network|local|sepolia|mainnet>
dincli auditor stake-DINtokens <Amount> --network <network|local|sepolia|mainnet>
dincli auditor registerAsAuditor --dinTaskAuditor-Address <dinTaskAuditor-Address> --network <network|local|sepolia|mainnet>
dincli auditor getmyAuditorLMS <GI> --dinTaskAuditor-Address <dinTaskAuditor-Address>  --network <network|local|sepolia|mainnet>
dincli auditor evaluate-LMS --client-adress <client-adress> --AuditingScheme <AuditingScheme> --dinTaskAuditor-Address <dinTaskAuditor-Address> --network <network|local|sepolia|mainnet>


dincli client download-initial-GM --dinTaskCoordinator-Address <dinTaskCoordinator-Address> --network <network|local|sepolia|mainnet>
dincli client download-latest-GM --dinTaskCoordinator-Address <dinTaskCoordinator-Address> --network <network|local|sepolia|mainnet>
dincli client download-training-scheme --dinTaskCoordinator-Address <dinTaskCoordinator-Address> --network <network|local|sepolia|mainnet>
dincli client create-LM-submission --initial-GM <initial-GM.pkl> --latest-GM <latest-GM.pkl> --training-scheme <training-scheme.pkl>
dincli client upload-LMS --LMS <LMS.pkl> --dinTaskCoordinator-Address <dinTaskCoordinator-Address> --network <network|local|sepolia|mainnet>







