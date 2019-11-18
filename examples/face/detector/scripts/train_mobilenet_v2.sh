#!/bin/sh
if ! test -f ../prototxt/mobilenet_v2/train_mobilenet_v2.prototxt ;then
	echo "error: ../prototxt/mobilenet_v2/train_mobilenet_v2.prototxt does not exit."
	echo "please generate your own model prototxt primarily."
        exit 1
fi
if ! test -f ../prototxt/mobilenet_v2/test_mobilenet_v2.prototxt ;then
	echo "error: ../prototxt/mobilenet_v2/test_mobilenet_v2.prototxt does not exit."
	echo "please generate your own model prototxt primarily."
        exit 1
fi
../../../../build/tools/caffe train --solver=../prototxt/mobilenet_v2/solver_train_mobilenet_v2.prototxt -gpu 1 \
#--snapshot=../snapshot/face_v3_iter_44807.solverstate