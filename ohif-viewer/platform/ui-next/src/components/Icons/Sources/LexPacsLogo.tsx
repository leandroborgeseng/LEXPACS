import React from 'react';
import type { IconProps } from '../types';

const RED = '#CC0000';
const BLACK = '#0A0A0A';
const WHITE = '#F5F5F5';
const GRAY = '#9CA3AF';

export const LexPacsLogo = (props: IconProps) => (
  <svg
    width="128px"
    height="28px"
    viewBox="0 0 128 28"
    xmlns="http://www.w3.org/2000/svg"
    aria-label="LEX PACS"
    {...props}
  >
    <rect
      x="0"
      y="2"
      width="24"
      height="24"
      rx="4"
      fill={BLACK}
      stroke="#262626"
      strokeWidth="1"
    />
    <path
      d="M5 8h5v2H7v3H5V8zm14 0h2v7h-2v-3h-3v-2h3v-2z"
      fill={RED}
    />
    <path
      d="M5 20h2v-3h3v-2H5v5zm14-5h-3v2h3v3h2v-7h-2z"
      fill={RED}
    />
    <rect
      x="10.5"
      y="9"
      width="3"
      height="10"
      rx="0.5"
      fill={RED}
    />
    <rect
      x="7"
      y="12.5"
      width="10"
      height="3"
      rx="0.5"
      fill={RED}
    />
    <text
      x="30"
      y="19"
      fontFamily="Roboto, Inter, sans-serif"
      fontSize="15"
      fontWeight="700"
      letterSpacing="0.04em"
      fill={RED}
    >
      LEX
    </text>
    <text
      x="68"
      y="19"
      fontFamily="Roboto, Inter, sans-serif"
      fontSize="15"
      fontWeight="600"
      letterSpacing="0.12em"
      fill={WHITE}
    >
      PACS
    </text>
    <rect
      x="63"
      y="8"
      width="1"
      height="12"
      fill={GRAY}
      opacity="0.5"
    />
  </svg>
);

export default LexPacsLogo;
