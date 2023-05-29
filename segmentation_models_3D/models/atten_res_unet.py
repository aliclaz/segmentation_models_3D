# -*- coding: utf-8 -*-
"""AttentionResUnet_backbone_model.py

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1M7V69reoYGV_X4oRdMlqeVaruU1TTaU2
"""

from keras_applications import get_submodules_from_kwargs

from ._common_blocks import Conv3dBn
from ._utils import freeze_model
from ..backbones.backbones_factory import Backbones

backend = None
layers = None
models = None
keras_utils = None

# ---------------------------------------------------------------------
#  Utility functions
# ---------------------------------------------------------------------

def get_submodules():
    return {
        'backend': backend,
        'models': models,
        'layers': layers,
        'utils': keras_utils,
    }

# ---------------------------------------------------------------------
#  Blocks
# ---------------------------------------------------------------------

def Conv3x3BnReLU(filters, use_batchnorm, name=None):
    kwargs = get_submodules()

    def wrapper(input_tensor):
        return Conv3dBn(
            filters,
            kernel_size=3,
            activation='relu',
            kernel_initializer='he_uniform',
            padding='same',
            use_batchnorm=use_batchnorm,
            name=name,
            **kwargs
        )(input_tensor)

    return wrapper

def ResConvBlock(filters, use_batchnorm=False, name=None):
    kwargs = get_submodules()

    def wrapper(input_tensor):
        x = Conv3x3BnReLU(filters, use_batchnorm, name=None)(input_tensor)
        x = Conv3x3BnReLU(filters, use_batchnorm, name=None)(x)
        shortcut = Conv3dBn(filters, 1, kernel_initializer='he_uniform', padding='same', use_batchnorm=use_batchnorm, name=name, **kwargs)(input_tensor)
        x = layers.add([shortcut, x])
        x = layers.Activation('relu')(x)

        return x
    return wrapper

def RepeatElement(tensor, rep):
    return layers.Lambda(lambda x, repnum: backend.repeat_elements(x, repnum,
                                                                    axis=3),
                         arguments={'repnum': rep})(tensor)

def GatingSignal(input, filters, use_batchnorm=False, name=None):
    x = layers.Conv3D(filters, (1, 1, 1), padding='same')(input)
    if use_batchnorm:
        x = layers.BatchNormalization()(x)
    x = layers.Activation('relu')(x)

    return x

def AttentionBlock(x, gating, inter_shape, name=None):
    shape_x = backend.int_shape(x)
    shape_g = backend.int_shape(gating)

    theta_x = layers.Conv3D(inter_shape, (2, 2, 2), strides=(2, 2, 2),padding='same')(x)
    shape_theta_x = backend.int_shape(theta_x) 

    phi_g = layers.Conv3D(inter_shape, (1, 1, 1), padding='same')(gating)
    upsample_g = layers.Conv3DTranspose(inter_shape, (3, 3, 3), strides=(shape_theta_x[1] // shape_g[1], shape_theta_x[2] // shape_g[2], 
                                                                         shape_theta_x[3] // shape_g[3]),
                                        padding='same')(phi_g)
    
    concat_xg = layers.add([upsample_g, theta_x])
    act_xg = layers.Activation('relu')(concat_xg)
    psi = layers.Conv3D(1, (1, 1, 1), padding='same')(act_xg)
    sigmoid_xg = layers.Activation('sigmoid')(psi)
    shape_sigmoid = backend.int_shape(sigmoid_xg)
    upsample_psi = layers.UpSampling3D(size=(shape_x[1] // shape_sigmoid[1], shape_x[2] // shape_sigmoid[2], shape_x[3] // shape_sigmoid[3]))(sigmoid_xg)
                                             
    upsample_psi = RepeatElement(upsample_psi, shape_x[4])

    y = layers.multiply([upsample_psi, x])

    result = layers.Conv3D(shape_x[4], (1, 1, 1), padding='same')(y)
    result_bn = layers.BatchNormalization()(result)
    
    return result_bn

def DecoderBlock(filters, stage, use_batchnorm=False):
    gate_name = 'decoder_stage{}_gating'.format(stage)
    atten_name = 'decoder_stage{}_attention'.format(stage)
    up_name = 'decoder_stage{}_upsampling'.format(stage)
    res_conv1_name = 'decoder_stage{}a'.format(stage)
    res_conv2_name = 'decoder_stage{}b'.format(stage)
    concat_name = 'decoder_stage{}_concat'.format(stage)

    concat_axis = 4 if backend.image_data_format() == 'channels_last' else 1

    def wrapper(input_tensor, skip=None):
        g = GatingSignal(input_tensor, filters, use_batchnorm, name=gate_name)
        atten = AttentionBlock(skip, g, filters, name=atten_name)
        x = layers.UpSampling3D(size=2, name=up_name)(input_tensor)

        if skip is not None:
            x = layers.Concatenate(axis=concat_axis, name=concat_name)([atten, skip])

        x = ResConvBlock(filters, use_batchnorm, name=res_conv1_name)(x)
        x = ResConvBlock(filters, use_batchnorm, name=res_conv2_name)(x)

        return x

    return wrapper

# ---------------------------------------------------------------------
#  Unet Decoder
# ---------------------------------------------------------------------

def build_atten_res_unet(
        backbone,
        skip_connection_layers,
        decoder_filters=(256, 128, 64, 32, 16),
        n_upsample_blocks=5,
        classes=1,
        activation='sigmoid',
        use_batchnorm=True,
        dropout=None,
):
    input_ = backbone.input
    x = backbone.output
    shape = x.shape

    # extract skip connections
    skips = ([backbone.get_layer(name=i).output if isinstance(i, str)
              else backbone.get_layer(index=i).output for i in skip_connection_layers])

    # add center block if previous operation was maxpooling (for vgg models)
    if isinstance(backbone.layers[-1], layers.MaxPooling3D):
        x = ResConvBlock(512, use_batchnorm, name='center_block1')(x)

    # building decoder blocks
    for i in range(n_upsample_blocks):

        if i < len(skips):
            skip = skips[i]
        else:
            skip = None

        x = DecoderBlock(decoder_filters[i], stage=i, use_batchnorm=use_batchnorm)(x, skip)

    if dropout:
        x = layers.SpatialDropout3D(dropout, name='pyramid_dropout')(x)

    # model head (define number of output classes)
    x = layers.Conv3D(
        filters=classes,
        kernel_size=(3, 3, 3),
        padding='same',
        use_bias=True,
        kernel_initializer='glorot_uniform',
        name='final_conv',
    )(x)
    x = layers.Activation(activation, name=activation)(x)

    # create keras model instance
    model = models.Model(input_, x)

    return model

# ---------------------------------------------------------------------
#  Unet Model
# ---------------------------------------------------------------------

def AttentionResUnet(
        backbone_name='vgg16',
        input_shape=(None, None, 3),
        classes=1,
        activation='sigmoid',
        weights=None,
        encoder_weights='imagenet',
        encoder_freeze=False,
        encoder_features='default',
        decoder_filters=(256, 128, 64, 32, 16),
        decoder_use_batchnorm=True,
        dropout=None,
        **kwargs
):
    """ Unet_ is a fully convolution neural network for image semantic segmentation
    Args:
        backbone_name: name of classification model (without last dense layers) used as feature
            extractor to build segmentation model.
        input_shape: shape of input data/image ``(H, W, C)``, in general
            case you do not need to set ``H`` and ``W`` shapes, just pass ``(None, None, C)`` to make your model be
            able to process images af any size, but ``H`` and ``W`` of input images should be divisible by factor ``32``.
        classes: a number of classes for output (output shape - ``(h, w, classes)``).
        activation: name of one of ``keras.activations`` for last model layer
            (e.g. ``sigmoid``, ``softmax``, ``linear``).
        weights: optional, path to model weights.
        encoder_weights: one of ``None`` (random initialization), ``imagenet`` (pre-training on ImageNet).
        encoder_freeze: if ``True`` set all layers of encoder (backbone model) as non-trainable.
        encoder_features: a list of layer numbers or names starting from top of the model.
            Each of these layers will be concatenated with corresponding decoder block. If ``default`` is used
            layer names are taken from ``DEFAULT_SKIP_CONNECTIONS``.
        decoder_block_type: one of blocks with following layers structure:
            - `upsampling`:  ``UpSampling2D`` -> ``Conv2D`` -> ``Conv2D``
            - `transpose`:   ``Transpose2D`` -> ``Conv2D``
        decoder_filters: list of numbers of ``Conv2D`` layer filters in decoder blocks
        decoder_use_batchnorm: if ``True``, ``BatchNormalisation`` layer between ``Conv2D`` and ``Activation`` layers
            is used.
    Returns:
        ``keras.models.Model``: **AttentionResUnet**
    .. _Unet:
        https://arxiv.org/pdf/1505.04597
    """

    global backend, layers, models, keras_utils
    backend, layers, models, keras_utils = get_submodules_from_kwargs(kwargs)

    backbone = Backbones.get_backbone(
        backbone_name,
        input_shape=input_shape,
        weights=encoder_weights,
        include_top=False,
        **kwargs,
    )

    if encoder_features == 'default':
        encoder_features = Backbones.get_feature_layers(backbone_name, n=4)

    model = build_atten_res_unet(
        backbone=backbone,
        skip_connection_layers=encoder_features,
        decoder_filters=decoder_filters,
        classes=classes,
        activation=activation,
        n_upsample_blocks=len(decoder_filters),
        use_batchnorm=decoder_use_batchnorm,
        dropout=dropout,
    )

    # lock encoder weights for fine-tuning
    if encoder_freeze:
        freeze_model(backbone, **kwargs)

    # loading model weights
    if weights is not None:
        model.load_weights(weights)

    return model