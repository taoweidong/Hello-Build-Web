# 第四轮代码质量优化实施计划（2026-10-15）

> 设计文档：`docs/superpowers/specs/2026-10-15-code-quality-optimization-round4-design.md`
> 评估报告：`docs/code-quality-assessment-2026-10-15.md`
> 纪律：每阶段完成后全量测试通过才进入下一阶段；禁止带失败提交。

## 阶段一：后端「高」（契约破坏 / 功能性 bug）

- [x] R4-B1 admin 删除策略补 pending 借用流拦截（共享 delete_strategy 服务函数）（+测试）
- [x] R4-B2 分支删除 ProtectedError → 40903 兜底（+测试）
- [x] R4-B3 slot_booking partial_update / branch permissions 非 dict body 归一（+测试）
- [x] 阶段回归：后端全量测试通过（474 例 OK）

## 阶段二：后端「中」（并发 / 审计 / 一致性）

- [x] R4-B4 conclusion note 走 body_str + max_len 255（+测试）
- [x] R4-B5 create_version/update_version 拒绝停用 PM（+测试）
- [x] R4-B6 login/logout 方法守卫（+测试）
- [x] R4-B7 security_log username 截断 100（+测试）
- [x] R4-B8 抢占/改期 IntegrityError 精确匹配 uniq_slot_booking_active（+测试）
- [x] R4-B9 config PUT 先全量校验后原子写入 + set_config 竞态兜底（+测试）
- [x] R4-B10 字符串字段 max_length 校验补全（拒绝超长 42201；借用拼接名 [:200]）（+测试）
- [x] R4-B11 StrategyAdmin.save_model 走服务层校验（+测试）
- [x] 阶段回归：后端全量测试通过（474 例 OK）

## 阶段三：后端「低」清理 + 测试补全

- [x] R4-B12 valid_hhmm/validate_weekdays 拒绝全角数字（+测试）
- [x] R4-B13 借用流列表可选分页 paginate_qs（+测试）
- [x] R4-B14 借用流单条路径 select_related（+assertNumQueries）
- [x] R4-B15 seed master 分支缺失守卫（+测试）
- [x] R4-B16 stop_instance 条件 UPDATE（+测试）
- [x] R4-B17 模板创建并发重名 IntegrityError → 40902（+测试）
- [x] R4-B18 登录失败计数 add+incr 原子化 + 注释修正（+测试）
- [x] R4-B19 双写校验口径漂移锁定测试（serializer vs create_booking）
- [x] 阶段回归：后端全量测试通过（474 例 OK）

## 阶段四：前端「高」

- [x] R4-F1 panorama 策略缓存版本键控 + invalidateStrategyCache（+测试）
- [x] R4-F2 批量释放他人条目收集统一原因 + 汇总分级（+测试）
- [x] R4-F3 UsersTab/TemplatesTab 补 :loading 在途守卫（+测试）
- [x] 阶段回归：前端 vitest + typecheck 通过（332 例全绿）

## 阶段五：前端「中」

- [x] R4-F4 ReportHeader 周日边界 today 判定解耦 elapsed（+测试）
- [x] R4-F5 copyText 走 utils/clipboard + 借用文案收敛 format.ts（+测试）
- [x] R4-F6 星期文案唯一来源接线（s2/s5 dayTitle、useScheduleData 副本删除）+ mondayOf 导出（+测试）
- [x] R4-F7 created_at 三处统一 formatTime（+测试）
- [x] R4-F8 permissionsOf 改调 canEditPanorama、durationOf 单一来源（+测试）
- [x] R4-F9 查询处理器收敛 usePanoramaPage，五布局去重（+测试）
- [x] R4-F10 eventActions.spec 补全（权限组合/顺序/withCopyAction）
- [x] R4-F11 改期弹窗 rescheduling 在途守卫 + :loading（+测试）
- [x] 阶段回归：前端 vitest + typecheck 通过（332 例全绿）

## 阶段六：前端「低」清理 + 测试补全

- [x] R4-F12 http.ts 401 跳转走 appHashUrl（+测试）
- [x] R4-F13 panorama/slot 清理集（groupByBranch 接线、countPendingApproval 删除、handled 事件处置、autoRefreshMs 删除、DEFAULT_HORIZON_DAYS 单一来源、horizonEndOf dayjs 化、router.push query、monthsOf 截断提示、borrow-flow cancelled 筛选、StrategyEditDialog 降级重试）（+测试）
- [x] R4-F14 残留 any 清理（http.ts/login/report detail）
- [x] 阶段回归：前端 vitest + typecheck + build 通过（332 例全绿）

## 阶段七：收尾

- [x] AGENTS.md：测试基线数字、第四轮报告/spec 索引、tests_quality_round4.py、「新功能合入前质量清单自检」纪律、panorama 域新约定
- [x] README.md 测试例数快照同步（474/332）
- [x] 受影响 feature spec 补修订记录（scheduling-panorama-design.md 修订六；另补 borrow-flow / slot-booking / branch-config / weekly-report 四份 2026-10-15 修订记录，并回填 2026-10-13 上线时仅记于全景 spec 的借用撤销与抢占改期端点）
- [x] `backend/uv.lock` 处置：加入 `.gitignore`（依赖声明唯一来源为 pyproject.toml，锁文件为本地 uv 运行产物；评估报告「其他观察」二选一裁定）
- [x] 全量门禁：后端 474 例 OK + 前端 332 例/typecheck/build/eslint 全绿
- [x] 简体中文 conventional commits 提交
