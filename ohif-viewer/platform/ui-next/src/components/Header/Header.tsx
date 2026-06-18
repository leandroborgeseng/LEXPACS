import React, { ReactNode } from 'react';
import classNames from 'classnames';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  Icons,
  Button,
  ToolButton,
} from '../';
import { IconPresentationProvider } from '@ohif/ui-next';

import NavBar from '../NavBar';

// Todo: we should move this component to composition and remove props base

interface HeaderProps {
  children?: ReactNode;
  menuOptions: Array<{
    title: string;
    icon?: string;
    onClick: () => void;
  }>;
  isReturnEnabled?: boolean;
  onClickReturnButton?: () => void;
  isSticky?: boolean;
  WhiteLabeling?: {
    createLogoComponentFn?: (React: any, props: any) => ReactNode;
  };
  PatientInfo?: ReactNode;
  Secondary?: ReactNode;
  UndoRedo?: ReactNode;
}

function Header({
  children,
  menuOptions,
  isReturnEnabled = true,
  onClickReturnButton,
  isSticky = false,
  WhiteLabeling,
  PatientInfo,
  UndoRedo,
  Secondary,
  ...props
}: HeaderProps): ReactNode {
  const onClickReturn = () => {
    if (isReturnEnabled && onClickReturnButton) {
      onClickReturnButton();
    }
  };

  return (
    <IconPresentationProvider
      size="large"
      IconContainer={ToolButton}
    >
      <NavBar
        isSticky={isSticky}
        {...props}
      >
        <div className="flex h-[48px] w-full flex-row items-center">
          {/* Zona esquerda */}
          <div className="flex shrink-0 items-center gap-2">
            <div
              className={classNames('inline-flex items-center gap-1', isReturnEnabled && 'cursor-pointer')}
              onClick={onClickReturn}
              data-cy="return-to-work-list"
            >
              {isReturnEnabled && <Icons.ArrowLeft className="text-foreground/60 hover:text-foreground h-5 w-5 transition-colors" />}
              <div>{WhiteLabeling?.createLogoComponentFn?.(React, props) || <Icons.LexPacsLogo />}</div>
            </div>
            {Secondary && <div className="ml-2 flex h-8 items-center">{Secondary}</div>}
          </div>

          {/* Zona central — toolbar primária */}
          <div className="flex flex-1 items-center justify-center gap-0.5 overflow-x-auto">
            {children}
          </div>

          {/* Zona direita */}
          <div className="flex shrink-0 select-none items-center gap-1">
            {UndoRedo && <>{UndoRedo}<div className="border-foreground/15 mx-1 h-5 border-r" /></>}
            {PatientInfo && <>{PatientInfo}<div className="border-foreground/15 mx-1 h-5 border-r" /></>}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon"
                  className="text-foreground/60 hover:text-foreground hover:bg-white/10 h-8 w-8">
                  <Icons.GearSettings className="h-5 w-5" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {menuOptions.map((option, index) => {
                  const IconComponent = option.icon ? Icons[option.icon as keyof typeof Icons] : null;
                  return (
                    <DropdownMenuItem key={index} onSelect={option.onClick}
                      className="flex items-center gap-2 py-2">
                      {IconComponent && <span className="flex h-4 w-4 items-center justify-center">
                        <Icons.ByName name={option.icon} /></span>}
                      <span className="flex-1">{option.title}</span>
                    </DropdownMenuItem>
                  );
                })}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </NavBar>
    </IconPresentationProvider>
  );
}

export default Header;
