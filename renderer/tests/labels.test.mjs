import test from 'node:test';
import assert from 'node:assert/strict';
import {overlaps,placeLabel} from '../../war_content/web/labels.mjs';
test('labels fit bounds, avoid units and other labels, or hide when no space remains',()=>{
 const bounds={x:0,y:0,width:300,height:300},anchor={x:150,y:150};
 const first=placeLabel(anchor,100,30,[],bounds);assert.ok(first);
 const second=placeLabel(anchor,100,30,[first],bounds);assert.ok(second);assert.equal(overlaps(first,second),false);
 assert.equal(placeLabel(anchor,400,300,[],bounds),null);
 assert.equal(placeLabel(anchor,100,30,[bounds],bounds),null);
});
