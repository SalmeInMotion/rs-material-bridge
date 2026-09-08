# RS Material Bridge -- node compatibility

Generated 2026-07-08 09:46 by tools/compat_report.py from the real node inventories of both apps:

- Houdini 21.0.700 (dumped 2026-07-08 09:37:19): 160 RS node classes
- C4D 2024400 (dumped 2026-07-06 20:45:50): 160 RS node classes

A class listed as portable means the *node* exists on both sides; individual parameters may still raise paste warnings (ramps, odd enums). Re-generate after Redshift updates -- the dumps refresh automatically on every Copy.

## Portable (exists in both) (158)

- `ambientocclusion`
- `architectural`
- `brick`
- `bumpblender`
- `bumpmap`
- `cameramap`
- `carpaint`
- `contour`
- `curvature`
- `displacement`
- `displacementblender`
- `distance`
- `distorter`
- `environment`
- `envswitch`
- `flakes`
- `fresnel`
- `golaemhsl`
- `hair`
- `hair2`
- `hairrandomcolor`
- `incandescent`
- `iortometaltints`
- `jitter`
- `light`
- `light_dome`
- `light_ies`
- `light_portal`
- `matcap`
- `material`
- `materialblender`
- `materiallayer`
- `matteshadow`
- `maxonnoise`
- `normalmap`
- `openpbrmaterial`
- `osl` -- aliased to Houdini's `rsosl`; the OSL source travels best-effort, dynamically created ports may not
- `particleattributelookup`
- `pavement`
- `physicalnightsky`
- `physicalsky`
- `physicalsun`
- `randomizedcolorswitch`
- `randomizedmaterialswitch`
- `rayswitch`
- `roundcorners`
- `rscolor2hsv`
- `rscolorcomposite`
- `rscolorconstant`
- `rscolorcorrection`
- `rscolorlayer`
- `rscolormaker`
- `rscolormix`
- `rscolorrange`
- `rscolorsplitter`
- `rshairposition`
- `rshsv2color`
- `rsmathabs`
- `rsmathabscolor`
- `rsmathabsvector`
- `rsmathacos`
- `rsmathadd`
- `rsmathaddvector`
- `rsmathasin`
- `rsmathatan`
- `rsmathatan2`
- `rsmathbias`
- `rsmathbiascolor`
- `rsmathbiasvector`
- `rsmathcos`
- `rsmathcrossvector`
- `rsmathdiv`
- `rsmathdivvector`
- `rsmathdotvector`
- `rsmathexp`
- `rsmathexpcolor`
- `rsmathexpvector`
- `rsmathfloor`
- `rsmathfloorvector`
- `rsmathfrac`
- `rsmathfracvector`
- `rsmathgain`
- `rsmathgaincolor`
- `rsmathgainvector`
- `rsmathinv`
- `rsmathinvcolor`
- `rsmathinvvector`
- `rsmathlengthvector`
- `rsmathln`
- `rsmathlnvector`
- `rsmathlog`
- `rsmathlogvector`
- `rsmathmax`
- `rsmathmaxvector`
- `rsmathmin`
- `rsmathminvector`
- `rsmathmix`
- `rsmathmixvector`
- `rsmathmod`
- `rsmathmodvector`
- `rsmathmul`
- `rsmathmulvector`
- `rsmathneg`
- `rsmathnegvector`
- `rsmathnormalizevector`
- `rsmathpow`
- `rsmathpowvector`
- `rsmathrange`
- `rsmathrangevector`
- `rsmathrcp`
- `rsmathrcpvector`
- `rsmathsaturate`
- `rsmathsaturatecolor`
- `rsmathsaturatevector`
- `rsmathsign`
- `rsmathsignvector`
- `rsmathsin`
- `rsmathsqrt`
- `rsmathsqrtvector`
- `rsmathsub`
- `rsmathsubcolor`
- `rsmathsubvector`
- `rsmathtan`
- `rsnoise`
- `rsramp` -- node travels, but ramp/curve knot values are not carried in v1 (reset to defaults on paste)
- `rsscalarconstant`
- `rsscalarramp` -- node travels, but ramp/curve knot values are not carried in v1 (reset to defaults on paste)
- `rsshaderswitch`
- `rsuserdatacolor`
- `rsuserdatainteger`
- `rsuserdatascalar`
- `rsuserdatastring`
- `rsuserdatavector`
- `rsvectormaker`
- `rsvectortoscalars`
- `skin`
- `sprite`
- `standardmaterial`
- `standardvolume`
- `state`
- `storecolortoaov`
- `storeintegertoaov`
- `storescalartoaov`
- `subsurfacescatter`
- `surfacetangent`
- `texturesampler`
- `tiles`
- `tonemappattern`
- `toonmaterial`
- `triplanar`
- `unitconversion`
- `uvcontextprojection`
- `uvprojection`
- `vertexattributelookup`
- `volume`
- `volumecolorattribute`
- `volumescalarattribute`
- `wireframe`

Aliased pairs (same node, different class name, bridged automatically): `osl` (C4D) = `rsosl` (Houdini)

## C4D only -- will NOT travel to Houdini (2)

C4D-native integrations without a Houdini counterpart.

- `c4dhairattribute`
- `reference`

## Houdini only -- will NOT travel to C4D (2)

- `shadermerge`
- `vopswitch`

## Not counted

- `output` -- the material Output node -- the bridge wires surface/displacement/volume outputs itself
