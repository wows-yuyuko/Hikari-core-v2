# 管理员配置说明

`check_version` / `update_style` / `update_ship` 三个指令**仅管理员可用**。

## 添加管理员流程

1. **启动**：机器人启动成功后（调用 `set_hikari_config` 完成初始化后），
   先把 `admin.txt` 中的管理员ID读入全局缓存（`load_admin_cache`），
   若不存在 `admin.txt` 则生成 32 位随机校验串输出到控制台：

   ```
   INFO | 管理员校验串已生成（请私信发送给机器人）：3f9a...
   ```

   校验串由 `hikari_core/core/admin.py::generate_check_admin`（独立生成器函数）生成，
   同时写入缓存目录 `get_cache_file()/checkAdmin.txt`。

2. **发送校验串**：用户把校验串**直接发送给机器人**（无需任何指令前缀，
   已移除 `wws add_admin` 指令）。建议通过**私信**发送，避免在群聊中泄露。

3. **验证 + 写入（统一入口）**：`verify_and_add_admin` 一步完成——
   - 发送者ID已在全局管理员缓存中 → 直接成功，不再走校验；
   - 否则比对 `checkAdmin.txt`（`verify_check_admin` 独立校验函数），
     通过后把发送者平台用户ID写入 `get_cache_file()/admin.txt`、
     删除 `checkAdmin.txt`，并同步更新全局缓存。

4. **再次启动**：检测到 `admin.txt` 已存在时不再生成校验串，管理员ID直接进全局缓存。

## SDK 接入端提示（重要）

- **建议走私信**：校验串属于一次性敏感凭证，请引导用户通过**私信（DM）**把校验串
  直接发送给机器人，避免在群聊中泄露。接入端需确保机器人收到的私信消息与群聊消息
  一样进入 `init_hikari` 指令流程（同一入口即可，无需额外逻辑）。
- 校验串只在「无 admin.txt」的首次启动时生成；若怀疑校验串已泄露，
  删除缓存目录下的 `admin.txt` 与 `checkAdmin.txt` 后重启，即可重新生成。
- 如需添加多名管理员，可手动在 `admin.txt` 中按行追加平台用户ID（重启后生效，
  或直接调用 `hikari_core.core.admin.load_admin_cache()` 热加载）。
