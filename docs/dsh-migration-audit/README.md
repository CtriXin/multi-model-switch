# MMS v4 起的 DSH 去留盘点（进行中）

任务：8b76aee15b3c41f7。范围是源码和历史盘点，不执行迁移、删除、fork 或发布。

固定基线：MMS v4 首个实现前 0d342c7f；main 54d3ff99；dev afd5575e；DSH ddefc45f（0.1.6-alpha.2）。PR 快照截至 #342。覆盖198个PR、702个唯一提交、221个merge节点。

交付要求：逐PR及合并台账；按当前需求与实际实现划分 plugin、定制发行/必要fork、可退役实现；保留独立MMS launcher和验证资产，避免把它们误归为可删除功能。区分DSH已知接口、迁移可行推断和未实测项。

原审计task 7b37a8aff257410b仍有其他active attempt，本次使用独立task避免覆盖。
