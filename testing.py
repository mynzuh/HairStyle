# import torch
# import torch.nn as nn
# import torch.nn.functional as F
# from collections import OrderedDict
# import numpy as np

# class MyLinear(nn.Module):
#     def __init__(self, input_size, output_size, gain=2**(0.5), use_wscale=False, lrmul=1, bias=True):
#         super().__init__()
#         he_std = gain * input_size**(-0.5)
#         if use_wscale:
#             init_std = 1.0 / lrmul
#             self.w_mul = he_std * lrmul
#         else:
#             init_std = he_std / lrmul
#             self.w_mul = lrmul
#         self.weight = torch.nn.Parameter(torch.randn(output_size, input_size) * init_std)
#         if bias:
#             self.bias = torch.nn.Parameter(torch.zeros(output_size))
#             self.b_mul = lrmul
#         else:
#             self.bias = None

#     def forward(self, x):
#         bias = self.bias
#         if bias is not None:
#             bias = bias * self.b_mul
#         return F.linear(x, self.weight * self.w_mul, bias)

# class MyConv2d(nn.Module):
#     def __init__(self, input_channels, output_channels, kernel_size, gain=2**(0.5), use_wscale=False, lrmul=1, bias=True,
#                  intermediate=None, upscale=False):
#         super().__init__()
#         self.upscale = Upscale2d() if upscale else None
#         he_std = gain * (input_channels * kernel_size ** 2) ** (-0.5)
#         self.kernel_size = kernel_size
#         if use_wscale:
#             init_std = 1.0 / lrmul
#             self.w_mul = he_std * lrmul
#         else:
#             init_std = he_std / lrmul
#             self.w_mul = lrmul
#         self.weight = torch.nn.Parameter(torch.randn(output_channels, input_channels, kernel_size, kernel_size) * init_std)
#         if bias:
#             self.bias = torch.nn.Parameter(torch.zeros(output_channels))
#             self.b_mul = lrmul
#         else:
#             self.bias = None
#         self.intermediate = intermediate

#     def forward(self, x):
#         bias = self.bias
#         if bias is not None:
#             bias = bias * self.b_mul
        
#         have_convolution = False
#         if self.upscale is not None and min(x.shape[2:]) * 2 >= 128:
#             w = self.weight * self.w_mul
#             w = w.permute(1, 0, 2, 3)
#             w = F.pad(w, (1,1,1,1))
#             w = w[:, :, 1:, 1:]+ w[:, :, :-1, 1:] + w[:, :, 1:, :-1] + w[:, :, :-1, :-1]
#             x = F.conv_transpose2d(x, w, stride=2, padding=(w.size(-1)-1)//2)
#             have_convolution = True
#         elif self.upscale is not None:
#             x = self.upscale(x)
            
#         if not have_convolution and self.intermediate is None:
#             return F.conv2d(x, self.weight * self.w_mul, bias, padding=self.kernel_size//2)
#         elif not have_convolution:
#             x = F.conv2d(x, self.weight * self.w_mul, None, padding=self.kernel_size//2)

#         if self.intermediate is not None:
#             x = self.intermediate(x)

#         if bias is not None:
#             x = x + bias.view(1, -1, 1, 1)
#         return x

# class Upscale2d(nn.Module):
#     def __init__(self):
#         super(Upscale2d, self).__init__()

#     def forward(self, x):
#         return F.interpolate(x, scale_factor=2, mode='bilinear', align_corners=False)

# class NoiseLayer(nn.Module):
#     def __init__(self, channels):
#         super().__init__()
#         self.weight = nn.Parameter(torch.zeros(channels))
#         self.noise = None
    
#     def forward(self, x, noise=None):
#         if noise is None and self.noise is None:
#             noise = torch.randn(x.size(0), 1, x.size(2), x.size(3), device=x.device, dtype=x.dtype)
#         elif noise is None:
#             noise = self.noise
#         x = x + self.weight.view(1, -1, 1, 1) * noise
#         return x

# class StyleMod(nn.Module):
#     def __init__(self, latent_size, channels, use_wscale):
#         super(StyleMod, self).__init__()
#         self.lin = MyLinear(latent_size, channels * 2, gain=1.0, use_wscale=use_wscale)

#     def forward(self, x, latent):
#         style = self.lin(latent)
#         shape = [-1, 2, x.size(1)] + (x.dim() - 2) * [1]
#         style = style.view(shape)
#         x = x * (style[:, 0] + 1.) + style[:, 1]
#         return x

# class PixelNormLayer(nn.Module):
#     def __init__(self, epsilon=1e-8):
#         super().__init__()
#         self.epsilon = epsilon

#     def forward(self, x):
#         return x * torch.rsqrt(torch.mean(x**2, dim=1, keepdim=True) + self.epsilon)

# class BlurLayer(nn.Module):
#     def __init__(self, kernel=[1, 2, 1], normalize=True, flip=False, stride=1):
#         super(BlurLayer, self).__init__()
#         kernel=[1, 2, 1]
#         kernel = torch.tensor(kernel, dtype=torch.float32)
#         kernel = kernel[:, None] * kernel[None, :]
#         kernel = kernel[None, None]
#         if normalize:
#             kernel = kernel / kernel.sum()
#         if flip:
#             kernel = kernel[:, :, ::-1, ::-1]
#         self.register_buffer('kernel', kernel)
#         self.stride = stride
  
#     def forward(self, x):
#         kernel = self.kernel.expand(x.size(1), -1, -1, -1)
#         x = F.conv2d(x, kernel, stride=self.stride, padding=int((self.kernel.size(2)-1)/2), groups=x.size(1))
#         return x

# class G_mapping(nn.Sequential):
#     def __init__(self, nonlinearity='lrelu', use_wscale=True):
#         act, gain = {'relu': (torch.relu, np.sqrt(2)),
#                      'lrelu': (nn.LeakyReLU(negative_slope=0.2), np.sqrt(2))}[nonlinearity]
#         layers = [
#             ('pixel_norm', PixelNormLayer()),
#             ('dense0', MyLinear(512, 512, gain=gain, lrmul=0.01, use_wscale=use_wscale)),
#             ('dense0_act', act),
#             ('dense1', MyLinear(512, 512, gain=gain, lrmul=0.01, use_wscale=use_wscale)),
#             ('dense1_act', act),
#             ('dense2', MyLinear(512, 512, gain=gain, lrmul=0.01, use_wscale=use_wscale)),
#             ('dense2_act', act),
#             ('dense3', MyLinear(512, 512, gain=gain, lrmul=0.01, use_wscale=use_wscale)),
#             ('dense3_act', act),
#             ('dense4', MyLinear(512, 512, gain=gain, lrmul=0.01, use_wscale=use_wscale)),
#             ('dense4_act', act),
#             ('dense5', MyLinear(512, 512, gain=gain, lrmul=0.01, use_wscale=use_wscale)),
#             ('dense5_act', act),
#             ('dense6', MyLinear(512, 512, gain=gain, lrmul=0.01, use_wscale=use_wscale)),
#             ('dense6_act', act),
#             ('dense7', MyLinear(512, 512, gain=gain, lrmul=0.01, use_wscale=use_wscale)),
#             ('dense7_act', act)
#         ]
#         super().__init__(OrderedDict(layers))
        
#     def forward(self, x):
#         x = super().forward(x)
#         x = x.unsqueeze(1).expand(-1, 18, -1)
#         return x

# class Truncation(nn.Module):
#     def __init__(self, avg_latent, max_layer=8, threshold=0.7):
#         super().__init__()
#         self.max_layer = max_layer
#         self.threshold = threshold
#         self.register_buffer('avg_latent', avg_latent)

#     def forward(self, x):
#         assert x.dim() == 3
#         interp = torch.lerp(self.avg_latent, x, self.threshold)
#         do_trunc = (torch.arange(x.size(1)) < self.max_layer).view(1, -1, 1)
#         return torch.where(do_trunc, interp, x)

# class LayerEpilogue(nn.Module):
#     def __init__(self, channels, dlatent_size, use_wscale, use_noise, use_pixel_norm, use_instance_norm, use_styles, activation_layer):
#         super().__init__()
#         layers = []
#         if use_noise:
#             layers.append(('noise', NoiseLayer(channels)))
#         layers.append(('activation', activation_layer))
#         if use_pixel_norm:
#             layers.append(('pixel_norm', PixelNormLayer()))
#         if use_instance_norm:
#             layers.append(('instance_norm', nn.InstanceNorm2d(channels)))
#         self.top_epi = nn.Sequential(OrderedDict(layers))
#         if use_styles:
#             self.style_mod = StyleMod(dlatent_size, channels, use_wscale=use_wscale)
#         else:
#             self.style_mod = None

#     def forward(self, x, dlatents_in_slice=None):
#         x = self.top_epi(x)
#         if self.style_mod is not None:
#             x = self.style_mod(x, dlatents_in_slice)
#         else:
#             assert dlatents_in_slice is None
#         return x

# class InputBlock(nn.Module):
#     def __init__(self, nf, dlatent_size, const_input_layer, gain, use_wscale, use_noise, use_pixel_norm, use_instance_norm, use_styles, activation_layer):
#         super().__init__()
#         self.const_input_layer = const_input_layer
#         self.nf = nf
#         if self.const_input_layer:
#             self.const = nn.Parameter(torch.ones(1, nf, 4, 4))
#             self.bias = nn.Parameter(torch.ones(nf))
#         else:
#             self.dense = MyLinear(dlatent_size, nf*16, gain=gain/4, use_wscale=use_wscale)
#         self.epi1 = LayerEpilogue(nf, dlatent_size, use_wscale, use_noise, use_pixel_norm, use_instance_norm, use_styles, activation_layer)
#         self.conv = MyConv2d(nf, nf, 3, gain=gain, use_wscale=use_wscale)
#         self.epi2 = LayerEpilogue(nf, dlatent_size, use_wscale, use_noise, use_pixel_norm, use_instance_norm, use_styles, activation_layer)
    
#     def forward(self, dlatents_in_range):
#         batch_size = dlatents_in_range.size(0)
#         if self.const_input_layer:
#             x = self.const.expand(batch_size, -1, -1, -1)
#             x = x + self.bias.view(1, -1, 1, 1)
#         else:
#             x = self.dense(dlatents_in_range[:, 0]).view(batch_size, self.nf, 4, 4)
#         x = self.epi1(x, dlatents_in_range[:, 0])
#         x = self.conv(x)
#         x = self.epi2(x, dlatents_in_range[:, 1])
#         return x

# class GSynthesisBlock(nn.Module):
#     def __init__(self, in_channels, out_channels, blur_filter, dlatent_size, gain, use_wscale, use_noise, use_pixel_norm, use_instance_norm, use_styles, activation_layer):
#         super().__init__()
#         if blur_filter:
#             blur = BlurLayer(blur_filter)
#         else:
#             blur = None
#         self.conv0_up = MyConv2d(in_channels, out_channels, kernel_size=3, gain=gain, use_wscale=use_wscale, intermediate=blur, upscale=True)
#         self.epi1 = LayerEpilogue(out_channels, dlatent_size, use_wscale, use_noise, use_pixel_norm, use_instance_norm, use_styles, activation_layer)
#         self.conv1 = MyConv2d(out_channels, out_channels, kernel_size=3, gain=gain, use_wscale=use_wscale)
#         self.epi2 = LayerEpilogue(out_channels, dlatent_size, use_wscale, use_noise, use_pixel_norm, use_instance_norm, use_styles, activation_layer)
            
#     def forward(self, x, dlatents_in_range):
#         x = self.conv0_up(x)
#         x = self.epi1(x, dlatents_in_range[:, 0])
#         x = self.conv1(x)
#         x = self.epi2(x, dlatents_in_range[:, 1])
#         return x

# class G_synthesis(nn.Module):
#     def __init__(self,
#         dlatent_size        = 512,          # Disentangled latent (W) dimensionality.
#         num_channels        = 3,            # Number of output color channels.
#         resolution          = 1024,         # Output resolution.
#         fmap_base           = 8192,         # Overall multiplier for the number of feature maps.
#         fmap_decay          = 1.0,          # log2 feature map reduction when doubling the resolution.
#         fmap_max            = 512,          # Maximum number of feature maps in any layer.
#         use_styles          = True,         # Enable style inputs?
#         const_input_layer   = True,         # First layer is a learned constant?
#         use_noise           = True,         # Enable noise inputs?
#         randomize_noise     = True,         # True = randomize noise inputs every time (non-deterministic), False = read noise inputs from variables.
#         nonlinearity        = 'lrelu',      # Activation function: 'relu', 'lrelu'
#         use_wscale          = True,         # Enable equalized learning rate?
#         use_pixel_norm      = False,        # Enable pixelwise feature vector normalization?
#         use_instance_norm   = True,         # Enable instance normalization?
#         dtype               = torch.float32,  # Data type to use for activations and outputs.
#         blur_filter         = [1, 2, 1],      # Low-pass filter to apply when resampling activations. None = no filtering.
#         ):
        
#         super().__init__()
#         def nf(stage):
#             return min(int(fmap_base / (2.0 ** (stage * fmap_decay))), fmap_max)
#         self.dlatent_size = dlatent_size
#         resolution_log2 = int(np.log2(resolution))
#         assert resolution == 2**resolution_log2 and resolution >= 4

#         act, gain = {'relu': (torch.relu, np.sqrt(2)),
#                      'lrelu': (nn.LeakyReLU(negative_slope=0.2), np.sqrt(2))}[nonlinearity]
#         blocks = []
#         last_channels = None
#         for res in range(2, resolution_log2 + 1):
#             channels = nf(res-1)
#             name = '{s}x{s}'.format(s=2**res)
#             if res == 2:
#                 blocks.append((name,
#                                InputBlock(channels, dlatent_size, const_input_layer, gain, use_wscale,
#                                           use_noise, use_pixel_norm, use_instance_norm, use_styles, act)))
#             else:
#                 blocks.append((name,
#                                GSynthesisBlock(last_channels, channels, blur_filter, dlatent_size, gain, use_wscale,
#                                                use_noise, use_pixel_norm, use_instance_norm, use_styles, act)))
#             last_channels = channels
#         self.torgb = MyConv2d(channels, num_channels, 1, gain=1, use_wscale=use_wscale)
#         self.blocks = nn.ModuleDict(OrderedDict(blocks))
    
#     def forward(self, dlatents_in):
#         for i, m in enumerate(self.blocks.values()):
#             if i == 0:
#                 x = m(dlatents_in[:, 2*i:2*i+2])
#             else:
#                 x = m(x, dlatents_in[:, 2*i:2*i+2])
#         rgb = self.torgb(x)
#         return rgb

# # 모델 초기화 및 가중치 파일 경로 설정
# device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
# resolution = 1024
# weight_file = r"E:\Users\Capstone\PyTorch-StyleGAN-Face-Editting\weights\karras2019stylegan-ffhq-1024x1024\karras2019stylegan-ffhq-1024x1024.pt"

# # 모델 초기화 및 가중치 로딩
# g_all = nn.Sequential(OrderedDict([
#     ('g_mapping', G_mapping()),
#     ('g_synthesis', G_synthesis(resolution=resolution))
# ]))
# g_all.load_state_dict(torch.load(weight_file, map_location=device))
# g_all.eval()
# g_all.to(device)

# # 사전 훈련된 가중치 로드 
# g_all.load_state_dict(torch.load(weight_file, map_location=device))

# # 모델을 평가 모드로 설정하고 적절한 장치로 이동
# g_all.eval()
# g_all.to(device)

# # g_mapping과 g_synthesis 변수를 사용하여 매핑 네트워크와 합성 네트워크에 접근할 수 있습니다.
# g_mapping, g_synthesis = g_all[0], g_all[1]



import torch
import torch.nn as nn
import torch.nn.functional as F
from collections import OrderedDict
import numpy as np
import cv2
import mediapipe as mp

class MyLinear(nn.Module):
    def __init__(self, input_size, output_size, gain=2**(0.5), use_wscale=False, lrmul=1, bias=True):
        super().__init__()
        he_std = gain * input_size**(-0.5)
        if use_wscale:
            init_std = 1.0 / lrmul
            self.w_mul = he_std * lrmul
        else:
            init_std = he_std / lrmul
            self.w_mul = lrmul
        self.weight = torch.nn.Parameter(torch.randn(output_size, input_size) * init_std)
        if bias:
            self.bias = torch.nn.Parameter(torch.zeros(output_size))
            self.b_mul = lrmul
        else:
            self.bias = None

    def forward(self, x):
        bias = self.bias
        if bias is not None:
            bias = bias * self.b_mul
        return F.linear(x, self.weight * self.w_mul, bias)

class MyConv2d(nn.Module):
    def __init__(self, input_channels, output_channels, kernel_size, gain=2**(0.5), use_wscale=False, lrmul=1, bias=True,
                 intermediate=None, upscale=False):
        super().__init__()
        self.upscale = Upscale2d() if upscale else None
        he_std = gain * (input_channels * kernel_size ** 2) ** (-0.5)
        self.kernel_size = kernel_size
        if use_wscale:
            init_std = 1.0 / lrmul
            self.w_mul = he_std * lrmul
        else:
            init_std = he_std / lrmul
            self.w_mul = lrmul
        self.weight = torch.nn.Parameter(torch.randn(output_channels, input_channels, kernel_size, kernel_size) * init_std)
        if bias:
            self.bias = torch.nn.Parameter(torch.zeros(output_channels))
            self.b_mul = lrmul
        else:
            self.bias = None
        self.intermediate = intermediate

    def forward(self, x):
        bias = self.bias
        if bias is not None:
            bias = bias * self.b_mul
        
        have_convolution = False
        if self.upscale is not None and min(x.shape[2:]) * 2 >= 128:
            w = self.weight * self.w_mul
            w = w.permute(1, 0, 2, 3)
            w = F.pad(w, (1,1,1,1))
            w = w[:, :, 1:, 1:]+ w[:, :, :-1, 1:] + w[:, :, 1:, :-1] + w[:, :, :-1, :-1]
            x = F.conv_transpose2d(x, w, stride=2, padding=(w.size(-1)-1)//2)
            have_convolution = True
        elif self.upscale is not None:
            x = self.upscale(x)
            
        if not have_convolution and self.intermediate is None:
            return F.conv2d(x, self.weight * self.w_mul, bias, padding=self.kernel_size//2)
        elif not have_convolution:
            x = F.conv2d(x, self.weight * self.w_mul, None, padding=self.kernel_size//2)

        if self.intermediate is not None:
            x = self.intermediate(x)

        if bias is not None:
            x = x + bias.view(1, -1, 1, 1)
        return x

class Upscale2d(nn.Module):
    def __init__(self):
        super(Upscale2d, self).__init__()

    def forward(self, x):
        return F.interpolate(x, scale_factor=2, mode='bilinear', align_corners=False)

class NoiseLayer(nn.Module):
    def __init__(self, channels):
        super().__init__()
        self.weight = nn.Parameter(torch.zeros(channels))
        self.noise = None
    
    def forward(self, x, noise=None):
        if noise is None and self.noise is None:
            noise = torch.randn(x.size(0), 1, x.size(2), x.size(3), device=x.device, dtype=x.dtype)
        elif noise is None:
            noise = self.noise
        x = x + self.weight.view(1, -1, 1, 1) * noise
        return x

class StyleMod(nn.Module):
    def __init__(self, latent_size, channels, use_wscale):
        super(StyleMod, self).__init__()
        self.lin = MyLinear(latent_size, channels * 2, gain=1.0, use_wscale=use_wscale)

    def forward(self, x, latent):
        style = self.lin(latent)
        shape = [-1, 2, x.size(1)] + (x.dim() - 2) * [1]
        style = style.view(shape)
        x = x * (style[:, 0] + 1.) + style[:, 1]
        return x

class PixelNormLayer(nn.Module):
    def __init__(self, epsilon=1e-8):
        super().__init__()
        self.epsilon = epsilon

    def forward(self, x):
        return x * torch.rsqrt(torch.mean(x**2, dim=1, keepdim=True) + self.epsilon)

class BlurLayer(nn.Module):
    def __init__(self, kernel=[1, 2, 1], normalize=True, flip=False, stride=1):
        super(BlurLayer, self).__init__()
        kernel=[1, 2, 1]
        kernel = torch.tensor(kernel, dtype=torch.float32)
        kernel = kernel[:, None] * kernel[None, :]
        kernel = kernel[None, None]
        if normalize:
            kernel = kernel / kernel.sum()
        if flip:
            kernel = kernel[:, :, ::-1, ::-1]
        self.register_buffer('kernel', kernel)
        self.stride = stride
  
    def forward(self, x):
        kernel = self.kernel.expand(x.size(1), -1, -1, -1)
        x = F.conv2d(x, kernel, stride=self.stride, padding=int((self.kernel.size(2)-1)/2), groups=x.size(1))
        return x

class G_mapping(nn.Sequential):
    def __init__(self, nonlinearity='lrelu', use_wscale=True):
        act, gain = {'relu': (torch.relu, np.sqrt(2)),
                     'lrelu': (nn.LeakyReLU(negative_slope=0.2), np.sqrt(2))}[nonlinearity]
        layers = [
            ('pixel_norm', PixelNormLayer()),
            ('dense0', MyLinear(512, 512, gain=gain, lrmul=0.01, use_wscale=use_wscale)),
            ('dense0_act', act),
            ('dense1', MyLinear(512, 512, gain=gain, lrmul=0.01, use_wscale=use_wscale)),
            ('dense1_act', act),
            ('dense2', MyLinear(512, 512, gain=gain, lrmul=0.01, use_wscale=use_wscale)),
            ('dense2_act', act),
            ('dense3', MyLinear(512, 512, gain=gain, lrmul=0.01, use_wscale=use_wscale)),
            ('dense3_act', act),
            ('dense4', MyLinear(512, 512, gain=gain, lrmul=0.01, use_wscale=use_wscale)),
            ('dense4_act', act),
            ('dense5', MyLinear(512, 512, gain=gain, lrmul=0.01, use_wscale=use_wscale)),
            ('dense5_act', act),
            ('dense6', MyLinear(512, 512, gain=gain, lrmul=0.01, use_wscale=use_wscale)),
            ('dense6_act', act),
            ('dense7', MyLinear(512, 512, gain=gain, lrmul=0.01, use_wscale=use_wscale)),
            ('dense7_act', act)
        ]
        super().__init__(OrderedDict(layers))
        
    def forward(self, x):
        x = super().forward(x)
        x = x.unsqueeze(1).expand(-1, 18, -1)
        return x

class Truncation(nn.Module):
    def __init__(self, avg_latent, max_layer=8, threshold=0.7):
        super().__init__()
        self.max_layer = max_layer
        self.threshold = threshold
        self.register_buffer('avg_latent', avg_latent)

    def forward(self, x):
        assert x.dim() == 3
        interp = torch.lerp(self.avg_latent, x, self.threshold)
        do_trunc = (torch.arange(x.size(1)) < self.max_layer).view(1, -1, 1)
        return torch.where(do_trunc, interp, x)

class LayerEpilogue(nn.Module):
    def __init__(self, channels, dlatent_size, use_wscale, use_noise, use_pixel_norm, use_instance_norm, use_styles, activation_layer):
        super().__init__()
        layers = []
        if use_noise:
            layers.append(('noise', NoiseLayer(channels)))
        layers.append(('activation', activation_layer))
        if use_pixel_norm:
            layers.append(('pixel_norm', PixelNormLayer()))
        if use_instance_norm:
            layers.append(('instance_norm', nn.InstanceNorm2d(channels)))
        self.top_epi = nn.Sequential(OrderedDict(layers))
        if use_styles:
            self.style_mod = StyleMod(dlatent_size, channels, use_wscale=use_wscale)
        else:
            self.style_mod = None

    def forward(self, x, dlatents_in_slice=None):
        x = self.top_epi(x)
        if self.style_mod is not None:
            x = self.style_mod(x, dlatents_in_slice)
        else:
            assert dlatents_in_slice is None
        return x

class InputBlock(nn.Module):
    def __init__(self, nf, dlatent_size, const_input_layer, gain, use_wscale, use_noise, use_pixel_norm, use_instance_norm, use_styles, activation_layer):
        super().__init__()
        self.const_input_layer = const_input_layer
        self.nf = nf
        if self.const_input_layer:
            self.const = nn.Parameter(torch.ones(1, nf, 4, 4))
            self.bias = nn.Parameter(torch.ones(nf))
        else:
            self.dense = MyLinear(dlatent_size, nf*16, gain=gain/4, use_wscale=use_wscale)
        self.epi1 = LayerEpilogue(nf, dlatent_size, use_wscale, use_noise, use_pixel_norm, use_instance_norm, use_styles, activation_layer)
        self.conv = MyConv2d(nf, nf, 3, gain=gain, use_wscale=use_wscale)
        self.epi2 = LayerEpilogue(nf, dlatent_size, use_wscale, use_noise, use_pixel_norm, use_instance_norm, use_styles, activation_layer)
    
    def forward(self, dlatents_in_range):
        batch_size = dlatents_in_range.size(0)
        if self.const_input_layer:
            x = self.const.expand(batch_size, -1, -1, -1)
            x = x + self.bias.view(1, -1, 1, 1)
        else:
            x = self.dense(dlatents_in_range[:, 0]).view(batch_size, self.nf, 4, 4)
        x = self.epi1(x, dlatents_in_range[:, 0])
        x = self.conv(x)
        x = self.epi2(x, dlatents_in_range[:, 1])
        return x

class GSynthesisBlock(nn.Module):
    def __init__(self, in_channels, out_channels, blur_filter, dlatent_size, gain, use_wscale, use_noise, use_pixel_norm, use_instance_norm, use_styles, activation_layer):
        super().__init__()
        if blur_filter:
            blur = BlurLayer(blur_filter)
        else:
            blur = None
        self.conv0_up = MyConv2d(in_channels, out_channels, kernel_size=3, gain=gain, use_wscale=use_wscale, intermediate=blur, upscale=True)
        self.epi1 = LayerEpilogue(out_channels, dlatent_size, use_wscale, use_noise, use_pixel_norm, use_instance_norm, use_styles, activation_layer)
        self.conv1 = MyConv2d(out_channels, out_channels, kernel_size=3, gain=gain, use_wscale=use_wscale)
        self.epi2 = LayerEpilogue(out_channels, dlatent_size, use_wscale, use_noise, use_pixel_norm, use_instance_norm, use_styles, activation_layer)
            
    def forward(self, x, dlatents_in_range):
        x = self.conv0_up(x)
        x = self.epi1(x, dlatents_in_range[:, 0])
        x = self.conv1(x)
        x = self.epi2(x, dlatents_in_range[:, 1])
        return x

class G_synthesis(nn.Module):
    def __init__(self,
        dlatent_size        = 512,          # Disentangled latent (W) dimensionality.
        num_channels        = 3,            # Number of output color channels.
        resolution          = 1024,         # Output resolution.
        fmap_base           = 8192,         # Overall multiplier for the number of feature maps.
        fmap_decay          = 1.0,          # log2 feature map reduction when doubling the resolution.
        fmap_max            = 512,          # Maximum number of feature maps in any layer.
        use_styles          = True,         # Enable style inputs?
        const_input_layer   = True,         # First layer is a learned constant?
        use_noise           = True,         # Enable noise inputs?
        randomize_noise     = True,         # True = randomize noise inputs every time (non-deterministic), False = read noise inputs from variables.
        nonlinearity        = 'lrelu',      # Activation function: 'relu', 'lrelu'
        use_wscale          = True,         # Enable equalized learning rate?
        use_pixel_norm      = False,        # Enable pixelwise feature vector normalization?
        use_instance_norm   = True,         # Enable instance normalization?
        dtype               = torch.float32,  # Data type to use for activations and outputs.
        blur_filter         = [1, 2, 1],      # Low-pass filter to apply when resampling activations. None = no filtering.
        ):
        
        super().__init__()
        def nf(stage):
            return min(int(fmap_base / (2.0 ** (stage * fmap_decay))), fmap_max)
        self.dlatent_size = dlatent_size
        resolution_log2 = int(np.log2(resolution))
        assert resolution == 2**resolution_log2 and resolution >= 4

        act, gain = {'relu': (torch.relu, np.sqrt(2)),
                     'lrelu': (nn.LeakyReLU(negative_slope=0.2), np.sqrt(2))}[nonlinearity]
        blocks = []
        last_channels = None
        for res in range(2, resolution_log2 + 1):
            channels = nf(res-1)
            name = '{s}x{s}'.format(s=2**res)
            if res == 2:
                blocks.append((name,
                               InputBlock(channels, dlatent_size, const_input_layer, gain, use_wscale,
                                          use_noise, use_pixel_norm, use_instance_norm, use_styles, act)))
            else:
                blocks.append((name,
                               GSynthesisBlock(last_channels, channels, blur_filter, dlatent_size, gain, use_wscale,
                                               use_noise, use_pixel_norm, use_instance_norm, use_styles, act)))
            last_channels = channels
        self.torgb = MyConv2d(channels, num_channels, 1, gain=1, use_wscale=use_wscale)
        self.blocks = nn.ModuleDict(OrderedDict(blocks))
    
    def forward(self, dlatents_in):
        for i, m in enumerate(self.blocks.values()):
            if i == 0:
                x = m(dlatents_in[:, 2*i:2*i+2])
            else:
                x = m(x, dlatents_in[:, 2*i:2*i+2])
        rgb = self.torgb(x)
        return rgb

def extract_facial_landmarks(image_path):
    mp_face_detection = mp.solutions.face_detection
    mp_drawing = mp.solutions.drawing_utils
    face_detection = mp_face_detection.FaceDetection()

    input_image = cv2.imread(image_path)
    input_image_rgb = cv2.cvtColor(input_image, cv2.COLOR_BGR2RGB)

    results = face_detection.process(input_image_rgb)

    landmarks = []
    if results.detections:
        for detection in results.detections:
            bboxC = detection.location_data.relative_bounding_box
            ih, iw, _ = input_image.shape
            x, y, w, h = int(bboxC.xmin * iw), int(bboxC.ymin * ih), int(bboxC.width * iw), int(bboxC.height * ih)
            bbox = (x, y, w, h)
            landmarks.append(bbox)
    
    return landmarks

# 모델 초기화 및 가중치 파일 경로 설정
device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
resolution = 1024
weight_file = r"E:\Users\Capstone\PyTorch-StyleGAN-Face-Editting\weights\karras2019stylegan-ffhq-1024x1024\karras2019stylegan-ffhq-1024x1024.pt"

# 모델 초기화 및 가중치 로딩
g_all = nn.Sequential(OrderedDict([
    ('g_mapping', G_mapping()),
    ('g_synthesis', G_synthesis(resolution=resolution))
]))
g_all.load_state_dict(torch.load(weight_file, map_location=device))
g_all.eval()
g_all.to(device)

# 사전 훈련된 가중치 로드 
g_all.load_state_dict(torch.load(weight_file, map_location=device))

# 모델을 평가 모드로 설정하고 적절한 장치로 이동
g_all.eval()
g_all.to(device)

# 이미지에서 얼굴 영역과 이목구비를 추출
image_path = "E:\\Users\\Capstone\\sample.jpeg"
face_landmarks = extract_facial_landmarks(image_path)

# 추출한 얼굴 영역과 이목구비를 시각화
image = cv2.imread(image_path)
for bbox in face_landmarks:
    x, y, w, h = bbox
    cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 2)
cv2.imshow('Facial Landmarks', image)
cv2.waitKey(0)
cv2.destroyAllWindows()
