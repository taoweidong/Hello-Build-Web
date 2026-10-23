"""序列化器包：仅保留仍有入参校验面契约的领域（时段抢占）。

2026-10-20 页面精简：报告/分支配置等域的序列化器随对应页面与端点删除；
策略域入参校验在 services.strategies（StrategyValidationError 口径），不经 DRF 序列化器。
"""