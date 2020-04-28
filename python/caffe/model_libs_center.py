import os,sys,logging
try:
    caffe_root = '/home/stive/workspace/caffe_train/'
    sys.path.insert(0, caffe_root + 'python')
    import caffe
except ImportError:
    logging.fatal("Cannot find caffe!")
from caffe import layers as L
from caffe import params as P
from caffe.proto import caffe_pb2
from caffe.model_libs import *

'''
def efficientDetBody(net, from_layer, alpha, beta, gamma, Use_BN = True):
    kwargs = {
            'param': [dict(lr_mult=1, decay_mult=1), dict(lr_mult=2, decay_mult=0)],
            'weight_filler': dict(type='xavier'),
            'bias_filler': dict(type='constant', value=0)}
    assert from_layer in net.keys()
'''
def MobilenetV2BottleBlock(net, from_layer, id, repeated_num, fileter_channels, strides, expansion_factor, 
                                    Use_BN = True, Use_scale = True, **bn_param):
    if strides == 1:
        out_layer_expand = "conv_{}_{}/{}".format(id, repeated_num, "expand")
        ConvBNLayer(net, from_layer, out_layer_expand, use_bn=Use_BN, use_relu = True,
                    num_output = fileter_channels * expansion_factor, kernel_size=1, 
                    pad=0, stride = strides, use_scale = Use_scale, **bn_param)
        out_layer_depthswise = "conv_{}_{}/{}".format(id, repeated_num, "depthwise")
        ConvBNLayer(net, out_layer_expand, out_layer_depthswise, use_bn=Use_BN, use_relu=True,
                    num_output = fileter_channels * expansion_factor, kernel_size=3, pad=1, 
                    group= fileter_channels * expansion_factor,
                    stride = strides, use_scale = Use_scale, **bn_param)
        out_layer_projects = "conv_{}_{}/{}".format(id, repeated_num, "linear")
        ConvBNLayer(net, out_layer_depthswise, out_layer_projects, use_bn=Use_BN, use_relu=False,
                    num_output = fileter_channels, kernel_size=1, pad=0, stride = strides, 
                    use_scale = Use_scale, **bn_param)
        res_name = 'Res_Sum_{}_{}'.format(id, repeated_num)
        net[res_name] = L.Eltwise(net[from_layer], net[out_layer_projects])
        return res_name
    elif strides == 2:
        out_layer_expand = "conv_{}_{}/{}".format(id, repeated_num, "expand")
        ConvBNLayer(net, from_layer, out_layer_expand, use_bn=Use_BN, use_relu=True,
                    num_output = fileter_channels * expansion_factor, kernel_size=1, pad=0, stride = 1, 
                    use_scale = Use_scale, **bn_param)
        out_layer_depthswise = "conv_{}_{}/{}".format(id, repeated_num, "depthwise")
        ConvBNLayer(net, out_layer_expand, out_layer_depthswise, use_bn=Use_BN, use_relu=True,
                    num_output = fileter_channels * expansion_factor, kernel_size=1, pad=0, stride = strides, 
                    group= fileter_channels * expansion_factor, use_scale = Use_scale, **bn_param)
        out_layer_projects = "conv_{}_{}/{}".format(id, repeated_num, "linear")
        ConvBNLayer(net, out_layer_depthswise, out_layer_projects, use_bn=Use_BN, use_relu=False,
                    num_output = fileter_channels, kernel_size=1, pad=0, stride = 1, use_scale = Use_scale,
                    **bn_param)
        return out_layer_projects           


def MobilenetV2Body(net, from_layer, Use_BN = True, **bn_param):
    assert from_layer in net.keys()
    index = 0
    out_layer = "conv_{}".format(index)
    ConvBNLayer(net, from_layer, out_layer, use_bn=Use_BN, use_relu=True,
                num_output= 32, kernel_size=3, pad=1, stride = 2, use_scale = True,
                **bn_param)
    index += 1
    ################################
    # t c  n s
    # - 32 1 2
    # 1 16 1 1
    # 6 24 2 2
    # 6 32 3 2
    # 6 64 4 2
    # 6 96 3 1
    # 6 160 3 2
    # 6 320 1 1
    ###############################
    Inverted_residual_setting = [[1, 16, 1, 1],
                                 [6, 24, 2, 2],
                                 [6, 32, 3, 2],
                                 [6, 64, 4, 2],
                                 [6, 96, 3, 1],
                                 [6, 160, 3, 2],
                                 [6, 320, 1, 1]]
    for _, (t, c, n, s) in enumerate(Inverted_residual_setting):
        if n > 1:
            if s == 2:
                layer_name = MobilenetV2BottleBlock(net, out_layer, index, 0, c, s, t, Use_BN = True, Use_scale = True, **bn_param)
                out_layer = layer_name
                index += 1
                strides = 1
                for id in range(n - 1):
                    layer_name = MobilenetV2BottleBlock(net, out_layer, index, id, c, strides, t, Use_BN = True, Use_scale = True, **bn_param)
                    out_layer = layer_name
                    index += 1
            elif s == 1:
                for id in range(n):
                    layer_name = MobilenetV2BottleBlock(net, out_layer, index, id, c, s, t, Use_BN = True, Use_scale = True, **bn_param)
                    out_layer = layer_name
                    index += 1
        elif n == 1:
            assert s == 1
            layer_name = MobilenetV2BottleBlock(net, out_layer, index, 0, c, s, t, Use_BN = True, Use_scale = True, **bn_param)
            out_layer = layer_name
            index += 1
    return net


def ResConnectBlock(net, from_layer_one, from_layer_two, stage_idx):
    res_name = "ResConnect_stage_{}".format(stage_idx)
    net[res_name] = L.Eltwise(net[from_layer_one], net[from_layer_two], operation = P.Eltwise.SUM)
    out_layer = "Dectction_stage_{}".format(stage_idx)
    ConvBNLayer(net, res_name, out_layer, use_bn = False, use_relu = False, 
                num_output= 6, kernel_size=1, pad = 0, 
                stride=1, use_scale = False, lr_mult=1)
    return res_name, out_layer


def CenterGridObjectLoss(net, bias_scale, low_bbox_scale, up_bbox_scale, 
                         stageidx, from_layers = [], net_height = 640, net_width = 640,
                         normalization_mode = P.Loss.VALID, num_classes= 2, loc_weight = 1.0, 
                         share_location = True, ignore_thresh = 0.3, class_type = P.CenterObject.SOFTMAX):
    center_object_loss_param = {
        'loc_weight': loc_weight,
        'num_class': num_classes,
        'share_location': share_location,
        'net_height': net_height,
        'net_width': net_width,
        'ignore_thresh': ignore_thresh,
        'bias_scale': bias_scale,
        'low_bbox_scale': low_bbox_scale,
        'up_bbox_scale': up_bbox_scale,
        'class_type': class_type,
    }
    loss_param = {
        'normalization': normalization_mode,
    }
    name = 'CenterGridLoss_{}'.format(stageidx)
    net[name] = L.CenterGridLoss(*from_layers, center_object_loss_param = center_object_loss_param,
                                 loss_param=loss_param, include=dict(phase=caffe_pb2.Phase.Value('TRAIN')),
                                 propagate_down=[True, False])


def CenterGridObjectDetect(net, from_layers = [], bias_scale = [], down_ratio = [], num_classes = 2,
                           ignore_thresh = 0.3,  keep_top_k = 200,
                           class_type = P.DetectionOutput.SOFTMAX, 
                           share_location = True, confidence_threshold = 0.15):
    det_out_param = {
        'num_classes': num_classes,
        'share_location': share_location,
        'keep_top_k': keep_top_k,
        'confidence_threshold': confidence_threshold,
        'class_type': class_type,
        'bias_scale': bias_scale,
        'down_ratio': down_ratio,
    }
    net.detection_out = L.CenterGridOutput(*from_layers, detection_output_param=det_out_param, 
                                                include=dict(phase=caffe_pb2.Phase.Value('TEST')))


def CenterGridMobilenetV2Body(net, from_layer, Use_BN = True, use_global_stats= False, **bn_param):
    assert from_layer in net.keys()
    index = 0
    feature_stride = [4, 8, 16, 32]
    accum_stride = 1
    pre_stride = 1
    LayerList_Name = []
    LayerList_Output = []
    LayerFilters = []
    out_layer = "conv_{}".format(index)
    ConvBNLayer(net, from_layer, out_layer, use_bn=Use_BN, use_relu=True,
                num_output= 32, kernel_size=3, pad=1, stride = 2, use_scale = True,
                **bn_param)
    accum_stride *= 2
    pre_channels= 32
    Inverted_residual_setting = [[1, 16, 1, 1],
                                 [6, 24, 2, 2],
                                 [6, 32, 3, 2],
                                 [6, 64, 4, 2],
                                 [6, 96, 3, 1],
                                 [6, 160, 3, 2],
                                 [6, 320, 1, 1]]
    for _, (t, c, n, s) in enumerate(Inverted_residual_setting):
        accum_stride *= s
        if n > 1:
            if s == 2:
                layer_name = MobilenetV2BottleBlock(net, out_layer, index, 0, c, s, t, Use_BN = True, 
                                                        Use_scale = True, **bn_param)
                out_layer = layer_name
                strides = 1
                for id in range(n - 1):
                    layer_name = MobilenetV2BottleBlock(net, out_layer, index, id + 1, c, strides, t, Use_BN = True, 
                                                        Use_scale = True, **bn_param)
                    out_layer = layer_name
            elif s == 1:
                Project_Layer = out_layer
                out_layer= "Conv_project_{}_{}".format(pre_channels, c)
                ConvBNLayer(net, Project_Layer, out_layer, use_bn = True, use_relu = True, 
                num_output= c, kernel_size= 3, pad= 1, stride= 1,
                lr_mult=1, use_scale=True)
                for id in range(n):
                    layer_name = MobilenetV2BottleBlock(net, out_layer, index, id, c, s, t, Use_BN = True, 
                                                        Use_scale = True, **bn_param)
                    out_layer = layer_name
        elif n == 1:
            assert s == 1
            Project_Layer = out_layer
            out_layer= "Conv_project_{}_{}".format(pre_channels, c)
            ConvBNLayer(net, Project_Layer, out_layer, use_bn = True, use_relu = True, 
                        num_output= c, kernel_size= 3, pad= 1, stride= 1,
                        lr_mult=1, use_scale=True)
            layer_name = MobilenetV2BottleBlock(net, out_layer, index, 0, c, s, t, Use_BN = True, 
                                                        Use_scale = True, **bn_param)
            out_layer = layer_name
        if accum_stride in feature_stride:
            if accum_stride != pre_stride:
                LayerList_Name.append(out_layer)
                LayerFilters.append(c)
            elif accum_stride == pre_stride:
                LayerList_Name[len(LayerList_Name) - 1] = out_layer
                LayerFilters[len(LayerFilters) - 1] = c
            pre_stride = accum_stride
        index += 1
        pre_channels = c
    assert len(LayerList_Name) == len(feature_stride)
    net_last_layer = net.keys()[-1]
    '''
    out_layer = "conv_1_expand"
    ConvBNLayer(net, net_last_layer, out_layer, use_bn = True, use_relu = True, 
                num_output= 512, kernel_size= 1, pad= 0, stride= 1,
                lr_mult=1, use_scale=True)
    net_last_layer = out_layer
    '''
    out_layer = "conv_1_project/DepthWise"
    ConvBNLayer(net, net_last_layer, out_layer, use_bn = True, use_relu = True, 
                num_output= 320, kernel_size= 3, pad= 1, stride= 2, group= 320,
                lr_mult=1, use_scale=True)
    net_last_layer = out_layer
    out_layer = "conv_1_project/linear"
    ConvBNLayer(net, net_last_layer, out_layer, use_bn = True, use_relu = True, 
                num_output= 320, kernel_size= 1, pad= 0, stride= 1,
                lr_mult=1, use_scale=True)
    for index in range(len(feature_stride)):
        #Deconv_layer scale up 2x2_s2
        channel_stage = LayerFilters[len(LayerFilters) - index - 1]
        net_last_layer = out_layer
        Reconnect_layer_one = "Deconv_Scale_Up_Stage_{}".format(channel_stage)
        ConvBNLayer(net, net_last_layer, Reconnect_layer_one, use_bn= True, use_relu = False, 
            num_output= channel_stage, kernel_size= 2, pad= 0, stride= 2,
            lr_mult=1, Use_DeConv= True, use_scale= True)
        
        # conv_layer linear 1x1
        net_last_layer= LayerList_Name[len(feature_stride) - index - 1]
        Reconnect_layer_two= "{}_linear".format(LayerList_Name[len(feature_stride) - index - 1])
        ConvBNLayer(net, net_last_layer, Reconnect_layer_two, use_bn= True, use_relu = False, 
            num_output= channel_stage, kernel_size= 1, pad= 0, stride= 1,
            lr_mult=1, use_scale= True)
        
        # eltwise_sum layer
        out_layer, detect_layer = ResConnectBlock(net, Reconnect_layer_one, Reconnect_layer_two, channel_stage)
        LayerList_Output.append(detect_layer)
    return net, LayerList_Output