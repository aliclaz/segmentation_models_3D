try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

setup(
    name='segmentation_models_3D',
    version='1.0.4',
    author='Roman Sol (ZFTurbo)',
    packages=['segmentation_models_3D', 'segmentation_models_3D/backbones', 'segmentation_models_3D/base', 'segmentation_models_3D/models'],
    url='https://github.com/aliclaz/segmentation_models_3D',
    description='Set of Keras models for segmentation of 3D volumes .',
    long_description='3D variants of popular models for segmentation like FPN, Unet, Linknet and PSPNet.'
                     'Models work with keras and tensorflow.keras.'
                     'More details: https://github.com/ZFTurbo/segmentation_models_3D',
    install_requires=[
        'tensorflow>=2.8.0',
        "keras_applications>=1.0.8",
        "classification_models_3D>=1.0.6",
    ],
)
