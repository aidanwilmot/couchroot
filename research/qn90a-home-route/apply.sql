BEGIN IMMEDIATE;
CREATE TEMP TABLE hub_guard (ok INTEGER CHECK (ok = 1));
INSERT INTO hub_guard SELECT count(*) = 1 FROM key_filter
 WHERE appid = 'com.samsung.tv.csfs' AND key = 'XF86Home';
INSERT INTO hub_guard SELECT count(*) = 1 FROM key_filter
 WHERE appid = 'com.samsung.tv.csfs' AND key = 'XF86Home'
 AND longpress IS NULL AND override IS NULL AND on_selector = ''
 AND request = 'launch' AND target_selector = 'package:com.samsung.tv.csfs'
 AND args = 'entry_point:smarthub_key';
INSERT INTO hub_guard SELECT count(*) = 0 FROM managed_app WHERE appid = 'MiniHub001.Hub';
UPDATE key_filter SET target_selector = 'package:MiniHub001.Hub', args = NULL
 WHERE appid = 'com.samsung.tv.csfs' AND key = 'XF86Home';
INSERT INTO managed_app (appid, ui_type, source) VALUES ('MiniHub001.Hub', NULL, NULL);
DROP TABLE hub_guard;
COMMIT;
