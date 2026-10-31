import test from 'node:test';
import assert from 'node:assert/strict';
import {designBounds,drawUnit} from '../../war_content/web/symbols.mjs';

test('unit bounds include outlines and asymmetric paths, ignoring unused canvas padding',()=>{
 const shape={primitives:[{kind:'rect',x:.3,y:-.1,width:.4,height:.2,stroke:'ink',stroke_width:.1}]};
 const b=designBounds(shape);assert.ok(Math.abs(b.x-.05)<1e-9);assert.ok(Math.abs(b.width-.5)<1e-9);
 assert.ok(Math.abs(b.y+.25)<1e-9);assert.ok(Math.abs(b.height-.3)<1e-9);
 const path=designBounds({primitives:[{kind:'line',points:[{x:-.9,y:-.5},{x:.5,y:.8}],stroke:'ink',stroke_width:.1}]});
 assert.ok(Math.abs(path.width-1.5)<1e-9);assert.ok(Math.abs(path.height-1.4)<1e-9);
});

test('unit renderer centers artwork and gives different silhouettes the requested diameter',()=>{
 const original=globalThis.PIXI;
 class Container{constructor(){this.children=[];this.position={set:(x,y)=>{this.x=x;this.y=y;}};this.scale={set:v=>{this.zoom=v;}};}addChild(v){this.children.push(v);}}
 class Graphics{roundRect(){return this;}fill(){return this;}stroke(){return this;}}
 globalThis.PIXI={Container,Graphics};
 try {
  for(const width of [.2,1.6]){
   const design={primitives:[{kind:'rect',x:0,y:0,width,height:.1,fill:'team',stroke:'none',stroke_width:0}]};
   const unit=drawUnit(design,0x477f92,48);
   assert.equal(unit.zoom*width*64,48);assert.equal(unit.children[0].x,0);assert.equal(unit.children[0].y,0);
  }
 }finally{globalThis.PIXI=original;}
});
