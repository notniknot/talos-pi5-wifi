ARG KERNEL_IMAGE
FROM ${KERNEL_IMAGE} AS kernel
FROM scratch
COPY --from=kernel /boot/Image /Image
COPY --from=kernel /usr/share/spdx/kernel.spdx.json /kernel.spdx.json
