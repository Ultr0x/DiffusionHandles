import pathlib

import torch
import scipy.ndimage
from omegaconf import OmegaConf

from diffhandles.stable_null_inverter import StableNullInverter
from diffhandles.guided_stable_diffuser import GuidedStableDiffuser
from diffhandles.depth_transform import transform_depth, depth_to_points, normalize_depth
from diffhandles.utils import solve_laplacian_depth


class DiffusionHandles:

    def __init__(self, conf_path=None):

        # TODO: use a single diffuser model for inversion and inference
        # TODO: even when not using a single diffuser model, make sure versions used for inversion and guided inference match
        self.diffuser_class = GuidedStableDiffuser
        self.diffuser = None
        # self.diffuser = None
        # self.inverter = NullInversion(self.diffuser)

        self.img_res = 512

        self.device = torch.device('cpu')

        # original
        # self.conf = OmegaConf.create({
        #     "bg_weight": 1.25,
        #     "fg_weight": 1.5
        #     })

        if conf_path is None:
            conf_path = f'{pathlib.Path(__file__).parent.resolve()}/config/default.yaml'
        
        self.conf = OmegaConf.load(conf_path)
        # pexels-matheus-bertelli-17109108_low.jpg
        

    def to(self, device: torch.device = None):
        # if self.depth_estimator is not None:
        #     self.depth_estimator.to(device=device)

        if self.diffuser is not None:
            self.diffuser.to(device=device)

        # if self.foreground_segmenter is not None:
        #     self.foreground_segmenter.sam.model.to(device=device)
        #     self.foreground_segmenter.device = device

        # if self.inpainter is not None:
        #     self.inpainter.to(device=device)

        self.device = device

    # def set_input_image(self, img: torch.Tensor, depth: torch.Tensor, prompt: str):
    #     """
    #     Set an input image. The following steps are performed:
    #     1) Invert the input image to get null text and noise that can reproduce the image.
    #     2) The image is reproduced using diffusion to get intermediate features (starting from the inverted noise and null text)
    #     Args:
    #         img: Input image.
    #         depth: Depth of the input image.
    #         prompt: Full prompt for the input image.

    #     Returns:
    #         inverted_null_text: The null text of the inverted input image.
    #         inverted_noise: The noise of the inverted input image.
    #         activations: Layer 1 activations from the first diffusion inference pass (from layer 1 of the decoder of the UNet).
    #         activations2: Layer 2 activations from the first diffusion inference pass (from layer 2 of the decoder of the UNet).
    #         activations3: Layer 3 activations from the first diffusion inference pass (from layer 3 of the decoder of the UNet).
    #         latent_image: A latent version of the generated image that reproduces the input image.
    #     """

    #     if self.diffuser is not None:
    #         del self.diffuser
    #         self.diffuser = None

    #     # get normalized disparity
    #     # TODO: depth should be converted to disparity and normalized in the diffuser, not here
    #     #       (since requiring dispairt and the normalization is specific to the depth-to-image diffuser)
    #     disparity = normalize_depth(1.0/depth)

    #     # invert image to get noise and null text that can be used to reproduce the image
    #     # TODO: Use the same diffuser as in the other steps here to avoid having to create two diffusers
    #     #       and to make sure the inverted noise and null text also work for the diffuser used in the other steps.
    #     diffuser = self.diffuser_class(custom_unet=False, conf=self.conf.guided_diffuser)
    #     diffuser.to(self.device)
    #     inverter = StableNullInverter(diffuser)
    #     _, inverted_noise, inverted_null_text = inverter.invert(
    #         target_img=img, depth=disparity, prompt=prompt, num_inner_steps=5 ,verbose=True)
    #     del inverter
    #     del diffuser

    #     # perform first diffusion inference pass to get intermediate features
    #     self.diffuser = self.diffuser_class(custom_unet=True, conf=self.conf.guided_diffuser)
    #     self.diffuser.to(self.device)
    #     with torch.no_grad():
    #         activations, activations2, activations3, latent_image = self.diffuser.initial_inference(
    #             latents=inverted_noise, depth=disparity, uncond_embeddings=inverted_null_text,
    #             prompt=prompt)

    #     return inverted_null_text, inverted_noise, activations, activations2, activations3, latent_image
        
    
    # def select_foreground(self, depth: torch.Tensor, fg_mask: torch.Tensor, bg_depth: torch.Tensor):
    #     """
    #     Select the foreground object in the image. The following steps are performed:
    #     1) The background depth is updated by infilling the hole in the depth of the input image

    #     Args:
    #         depth: Depth of the input image.
    #         fg_mask: A mask of the foreground object.
    #         bg_depth: Depth of the background (with removed foreground object).

    #     Returns:
    #         bg_depth: An updated background depth that has been adjusted to better match the depth of the input image.
    #     """

    #     # infill hole in the depth of the input image (where the foreground object used to be)
    #     # with the depth of the background image
    #     bg_depth = solve_laplacian_depth(
    #         depth[0, 0].cpu().numpy(),
    #         bg_depth[0, 0].cpu().numpy(),
    #         scipy.ndimage.binary_dilation(fg_mask[0, 0].cpu().numpy(), iterations=15))
    #     bg_depth = torch.from_numpy(bg_depth).to(device=self.device)[None, None]

    #     return bg_depth

    def set_foreground(self, img: torch.Tensor, depth: torch.Tensor, prompt: str, fg_mask: torch.Tensor, bg_depth: torch.Tensor):
        """
        Select the foreground object in the image. The following steps are performed:
        1) The background depth is updated by infilling the hole in the depth of the input image

        Args:
            depth: Depth of the input image.
            fg_mask: A mask of the foreground object.
            bg_depth: Depth of the background (with removed foreground object).

        Returns:
            bg_depth: An updated background depth that has been adjusted to better match the depth of the input image.
        """

        if self.diffuser is not None:
            del self.diffuser
            self.diffuser = None

        # infill hole in the depth of the input image (where the foreground object used to be)
        # with the depth of the background image
        bg_depth = solve_laplacian_depth(
            depth[0, 0].cpu().numpy(),
            bg_depth[0, 0].cpu().numpy(),
            scipy.ndimage.binary_dilation(fg_mask[0, 0].cpu().numpy(), iterations=15))
        bg_depth = torch.from_numpy(bg_depth).to(device=self.device)[None, None]

        bg_pts = depth_to_points(bg_depth, intrinsics=self.diffuser_class.get_depth_intrinsics(h=self.img_res, w=self.img_res))
        pts = depth_to_points(depth, intrinsics=self.diffuser_class.get_depth_intrinsics(h=self.img_res, w=self.img_res))

        # 3d-transform depth
        # TODO: this should work on and return unnormalized depth instead of normalized disparity
        disparity, target_mask, correspondences, raw_edited_depth = transform_depth(
            pts=pts, bg_pts=bg_pts, fg_mask=fg_mask,
            intrinsics=self.diffuser_class.get_depth_intrinsics(h=self.img_res, w=self.img_res).to(device=pts.device),
            img_res=self.img_res,
            rot_angle=0,
            rot_axis=torch.tensor([0.0, 1.0, 0.0]).to(self.device),
            translation=torch.tensor([0.0, 0.0, 0.0]).to(self.device),
            depth_bounds=None)

        # invert image to get noise and null text that can be used to reproduce the image
        # TODO: Use the same diffuser as in the other steps here to avoid having to create two diffusers
        #       and to make sure the inverted noise and null text also work for the diffuser used in the other steps.
        diffuser = self.diffuser_class(custom_unet=False, conf=self.conf.guided_diffuser)
        diffuser.to(self.device)
        inverter = StableNullInverter(diffuser)
        _, inverted_noise, inverted_null_text = inverter.invert(
            target_img=img, depth=disparity, prompt=prompt, num_inner_steps=5 ,verbose=True)
        del inverter
        del diffuser

        # perform first diffusion inference pass to get intermediate features
        self.diffuser = self.diffuser_class(custom_unet=True, conf=self.conf.guided_diffuser)
        self.diffuser.to(self.device)
        with torch.no_grad():
            activations, activations2, activations3, latent_image = self.diffuser.initial_inference(
                latents=inverted_noise, depth=disparity, uncond_embeddings=inverted_null_text,
                prompt=prompt)

        return bg_depth, inverted_null_text, inverted_noise, activations, activations2, activations3, latent_image

    def transform_foreground(
            self, depth: torch.Tensor, prompt: str,
            fg_mask:torch.Tensor, bg_depth: torch.Tensor,
            inverted_null_text: torch.Tensor, inverted_noise: torch.Tensor, 
            activations: torch.Tensor, activations2: torch.Tensor, activations3: torch.Tensor,
            rot_angle: float = None, rot_axis: torch.Tensor = None, translation: torch.Tensor = None,
            use_input_depth_normalization=False):
        """
        Move the foreground object. The following steps are performed:
        1) The depth of the foreground object and the intermediate features are 3D-transformed
        2) The edited image is generated guided by the 3D-transformed intermediate features

        Args:
            depth: Depth of the input image.
            prompt: Full prompt for the input image.
            fg_mask: A mask of the foreground object.
            bg_depth: Depth of the background (with removed foreground object).
            inverted_null_text: The null text of the inverted input image.
            inverted_noise: The noise of the inverted input image.
            activations: Layer 1 activations from the first diffusion inference pass (from layer 1 of the decoder of the UNet).
            activations2: Layer 2 activations from the first diffusion inference pass (from layer 2 of the decoder of the UNet).
            activations3: Layer 3 activations from the first diffusion inference pass (from layer 3 of the decoder of the UNet).
            rot_angle: Rotation angle in degrees.
            rot_axis: Rotation axis.
            translation: Translation vector.
            use_input_depth_normalization: Use the same normalization factor and bias as the input depth for the edited depth, to make the edited depth as similar to the input depth as possible.
        
        Returns:
            output_img: The edited image.
        """
        
        # get point clouds from depths
        bg_pts = depth_to_points(bg_depth, intrinsics=self.diffuser_class.get_depth_intrinsics(h=self.img_res, w=self.img_res))
        pts = depth_to_points(depth, intrinsics=self.diffuser_class.get_depth_intrinsics(h=self.img_res, w=self.img_res))

        # get normalized disparity
        # TODO: depth should be converted to disparity and normalized in the diffuser, not here
        #       (since requiring dispairt and the normalization is specific to the depth-to-image diffuser)
        if use_input_depth_normalization:
            depth, depth_bounds = normalize_depth(1.0/depth, return_bounds=True)
        
        # 3d-transform depth
        # TODO: this should work on and return unnormalized depth instead of normalized disparity
        edited_disparity, target_mask, correspondences, raw_edited_depth = transform_depth(
            pts=pts, bg_pts=bg_pts, fg_mask=fg_mask,
            intrinsics=self.diffuser_class.get_depth_intrinsics(h=self.img_res, w=self.img_res).to(device=pts.device),
            img_res=self.img_res,
            rot_angle=rot_angle,
            rot_axis=rot_axis,
            translation=translation,
            depth_bounds=depth_bounds if use_input_depth_normalization else None)

        if edited_disparity.shape[-2:] != (self.img_res, self.img_res):
            raise ValueError(f"Transformed depth must be of size {self.img_res}x{self.img_res}.")

        # perform second diffusion inference pass guided by the 3d-transformed features
        if self.diffuser is None:
            self.diffuser = self.diffuser_class(custom_unet=True, conf=self.conf.guided_diffuser)
            self.diffuser.to(self.device)
        with torch.no_grad():
            output_img = self.diffuser.guided_inference(
                latents=inverted_noise, depth=edited_disparity, uncond_embeddings=inverted_null_text,
                prompt=prompt,
                activations_orig=activations, activations2_orig=activations2, activations3_orig=activations3,
                correspondences=correspondences)

        return output_img, raw_edited_depth