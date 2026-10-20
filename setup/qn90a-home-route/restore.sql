BEGIN IMMEDIATE;
CREATE TEMP TABLE hub_guard (ok INTEGER CHECK (ok = 1));
INSERT INTO hub_guard SELECT count(*) = 1 FROM key_filter
 WHERE appid = 'com.samsung.tv.csfs' AND key = 'XF86Home';
INSERT INTO hub_guard SELECT count(*) = 1 FROM key_filter
 WHERE appid = 'com.samsung.tv.csfs' AND key = 'XF86Home'
 AND longpress IS NULL AND override IS NULL AND on_selector = ''
 AND request = 'launch' AND target_selector = 'package:MiniHub001.Hub' AND args IS NULL;
INSERT INTO hub_guard SELECT count(*) = 1 FROM managed_app WHERE appid = 'MiniHub001.Hub';
INSERT INTO hub_guard SELECT count(*) = 1 FROM managed_app
 WHERE appid = 'MiniHub001.Hub' AND ui_type IS NULL AND source IS NULL;
-- Remove the casting rule before unregistering its launch target.
INSERT INTO hub_guard SELECT count(*) = 0 FROM task_filter WHERE appid = 'MiniHub001.Hub';
UPDATE key_filter SET target_selector = 'package:com.samsung.tv.csfs', args = 'entry_point:smarthub_key'
 WHERE appid = 'com.samsung.tv.csfs' AND key = 'XF86Home';
DELETE FROM managed_app WHERE appid = 'MiniHub001.Hub' AND ui_type IS NULL AND source IS NULL;
DROP TABLE hub_guard;
COMMIT;
