import React from 'react';
import './Card.css';

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  hoverable?: boolean;
}

export default function Card({ 
  children, 
  className = '', 
  hoverable = false,
  onClick = undefined,
  ...props
}: CardProps) {
  return (
    <div 
      className={`card ${hoverable ? 'hoverable' : ''} ${className}`}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      {...props}
    >
      {children}
    </div>
  );
}
