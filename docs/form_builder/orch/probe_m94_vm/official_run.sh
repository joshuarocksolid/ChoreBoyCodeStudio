#!/bin/sh
# Interleaved A, B, A, B on one machine. A is this branch. B is feat/form-builder.
# FreeCAD 1.0. The probe turns the builder on. Do not set QT_QPA_PLATFORM.
unset QT_QPA_PLATFORM
unset CBCS_QT_API
export CBCS_DISABLE_BACKGROUND_RUNTIME=1

run_one() {
  name=$1
  root=$2
  echo "BEGIN $name $(date -u +%H:%M:%S)"
  /opt/freecad/AppRun -c "import runpy,sys; sys.argv=['run_probe.py','/tmp/m94out-$name']; sys.path.insert(0,'$root'); runpy.run_path('$root/run_probe.py', run_name='__main__')" > "/tmp/m94-$name-speed.out" 2>"/tmp/m94-$name-speed.err"
  echo "SPEED_EXIT $name $?"
  /opt/freecad/AppRun -c "import runpy,sys; sys.path.insert(0,'$root'); runpy.run_path('$root/fair_vm.py', run_name='__main__')" > "/tmp/m94-$name-fair.out" 2>"/tmp/m94-$name-fair.err"
  echo "FAIR_EXIT $name $?"
  echo "END $name $(date -u +%H:%M:%S)"
}

run_one A1 /mnt/cbprobe/incoming/m94/payload
run_one B1 /mnt/cbprobe/incoming/m94/fb_feat_payload
run_one A2 /mnt/cbprobe/incoming/m94/payload
run_one B2 /mnt/cbprobe/incoming/m94/fb_feat_payload
echo ALL_DONE
