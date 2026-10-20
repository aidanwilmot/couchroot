'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const Model=require('../web/model'),{convert}=require('../native-hub/import-web-state.cjs');
for(const vector of require('./fixtures/preferences.json'))test('shared preferences: '+vector.name,()=>{
 assert.equal(Model.clean(vector.apps).length,vector.web_count);
 assert.equal(Model.nativeApps(vector.apps),vector.native);
 const convertIt=()=>convert({[Model.KEY]:JSON.stringify({version:1,apps:vector.apps})});
 if(vector.native)assert.doesNotThrow(convertIt);else assert.throws(convertIt);
});
