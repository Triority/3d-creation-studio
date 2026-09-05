<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
const props=defineProps({url:String}); const host=ref(); let renderer,scene,camera,controls,frame,object
function resize(){if(!host.value||!renderer)return;const w=host.value.clientWidth,h=host.value.clientHeight;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix()}
function load(){if(object){scene.remove(object);object=null}if(!props.url)return;new GLTFLoader().load(props.url,g=>{object=g.scene;scene.add(object);const box=new THREE.Box3().setFromObject(object),size=box.getSize(new THREE.Vector3()),center=box.getCenter(new THREE.Vector3());object.position.sub(center);const span=Math.max(size.x,size.y,size.z)||1;camera.position.set(span*1.4,span*.9,span*1.4);camera.near=span/100;camera.far=span*100;camera.updateProjectionMatrix();controls.target.set(0,0,0);controls.update()})}
onMounted(()=>{scene=new THREE.Scene();scene.background=new THREE.Color(0xf2f5f6);camera=new THREE.PerspectiveCamera(38,1,.01,1000);renderer=new THREE.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.15;const pmrem=new THREE.PMREMGenerator(renderer);scene.environment=pmrem.fromScene(new RoomEnvironment(),.04).texture;pmrem.dispose();host.value.appendChild(renderer.domElement);controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;scene.add(new THREE.HemisphereLight(0xffffff,0x52606b,2.1));const key=new THREE.DirectionalLight(0xffffff,2.2);key.position.set(4,6,5);scene.add(key);const fill=new THREE.DirectionalLight(0xd9eeff,1.1);fill.position.set(-4,2,-3);scene.add(fill);const grid=new THREE.GridHelper(10,20,0xc8d0d5,0xdfe4e7);grid.position.y=-1;scene.add(grid);const tick=()=>{controls.update();renderer.render(scene,camera);frame=requestAnimationFrame(tick)};resize();tick();window.addEventListener('resize',resize);load()})
watch(()=>props.url,load);onBeforeUnmount(()=>{cancelAnimationFrame(frame);window.removeEventListener('resize',resize);controls?.dispose();renderer?.dispose()})
</script>
<template><div ref="host" class="viewer"><div v-if="!url" class="viewer-empty">选择一个历史模型后可在这里预览</div></div></template>
